# -*- coding: utf-8 -*-
"""
URL 调度器（Frontier）
管理待爬取 URL 的优先级队列
"""
import time
import threading
from collections import defaultdict
from heapq import heappush, heappop
from utils.logger import get_logger
from utils.url_utils import get_domain, normalize_url, url_to_docid

logger = get_logger('crawler.frontier')


class URLFrontier:
    """
    URL 调度队列
    实现了双队列架构：
    - 优先级前端队列（按重要性分带）
    - 每主机后端队列（保证礼貌性）
    """
    
    def __init__(self, db, max_per_host=3, politeness_delay=1.0):
        self.db = db
        self.max_per_host = max_per_host
        self.politeness_delay = politeness_delay
        
        # 内存中的优先级队列（小顶堆）
        # (priority, timestamp, url, depth)
        self._heap = []
        self._heap_lock = threading.Lock()
        
        # 每主机的最后请求时间
        self._host_last_request = {}
        self._host_lock = threading.Lock()
        
        # 每主机当前活跃请求数
        self._host_active_count = defaultdict(int)
        
        # Bloom filter 用于快速去重（URL 哈希集合）
        self._seen_urls = set()
        self._seen_lock = threading.Lock()
        
        # 统计
        self._stats = {
            'added': 0,
            'fetched': 0,
            'completed': 0,
            'failed': 0,
        }
    
    def add_url(self, url, depth=0, priority=5):
        """添加 URL 到队列"""
        url = normalize_url(url)
        
        # 快速去重检查
        with self._seen_lock:
            if url in self._seen_urls:
                return False
            self._seen_urls.add(url)
        
        # 添加到数据库
        success = self.db.add_url(url, depth, priority)
        if success:
            self._stats['added'] += 1
            # 添加到内存堆（用于快速调度）
            with self._heap_lock:
                heappush(self._heap, (priority, time.time(), url, depth))
        
        return success
    
    def add_urls(self, urls, depth=0, priority=5):
        """批量添加 URL"""
        count = 0
        for url in urls:
            if self.add_url(url, depth, priority):
                count += 1
        return count
    
    def get_next_url(self):
        """
        获取下一个可爬取的 URL
        考虑礼貌性延迟和每主机并发限制
        
        当某个主机被礼貌性延迟阻塞时，继续检查堆中其他主机的 URL，
        而不是直接放弃整个堆。
        """
        now = time.time()
        
        # 先尝试从内存堆中获取
        blocked_urls = []       # 暂存被阻塞的 URL
        checked_hosts = set()   # 已检查且被阻塞的主机（避免重复检查）
        
        with self._heap_lock:
            while self._heap:
                priority, ts, url, depth = heappop(self._heap)
                
                host = get_domain(url)
                
                # 如果该主机已被检查且被阻塞，直接暂存，跳过重复检查
                if host in checked_hosts:
                    blocked_urls.append((priority, ts, url, depth))
                    continue
                
                # 检查是否可以爬取（礼貌性 + 并发限制）
                if self._can_crawl_host(host, now):
                    self._mark_host_start(host)
                    self._stats['fetched'] += 1
                    # 将之前被阻塞的 URL 放回堆中
                    for item in blocked_urls:
                        heappush(self._heap, item)
                    return {
                        'url': url,
                        'depth': depth,
                        'priority': priority,
                    }
                else:
                    # 暂时不能爬取，标记该主机为已阻塞，暂存 URL，继续检查其他主机
                    checked_hosts.add(host)
                    blocked_urls.append((priority, ts, url, depth))
            
            # 堆中所有 URL 都被阻塞，将它们放回堆中
            for item in blocked_urls:
                heappush(self._heap, item)
        
        # 内存堆中没有可用的，从数据库获取
        result = self.db.get_next_url()
        if result:
            host = get_domain(result['url'])
            with self._host_lock:
                self._host_active_count[host] += 1
                self._host_last_request[host] = time.time()
            self._stats['fetched'] += 1
            return result
        
        return None
    
    def _can_crawl_host(self, host, now):
        """检查是否可以爬取该主机"""
        with self._host_lock:
            # 检查并发数
            if self._host_active_count.get(host, 0) >= self.max_per_host:
                return False
            
            # 检查礼貌性延迟
            last_req = self._host_last_request.get(host, 0)
            if now - last_req < self.politeness_delay:
                return False
            
            return True
    
    def _mark_host_start(self, host):
        """标记主机开始请求"""
        with self._host_lock:
            self._host_active_count[host] += 1
            self._host_last_request[host] = time.time()
    
    def mark_completed(self, url):
        """标记 URL 爬取完成"""
        self.db.mark_url_success(url)
        host = get_domain(url)
        with self._host_lock:
            if host in self._host_active_count:
                self._host_active_count[host] -= 1
                if self._host_active_count[host] <= 0:
                    del self._host_active_count[host]
        self._stats['completed'] += 1
    
    def mark_failed(self, url, retry=True):
        """标记 URL 爬取失败"""
        self.db.mark_url_failed(url, retry)
        host = get_domain(url)
        with self._host_lock:
            if host in self._host_active_count:
                self._host_active_count[host] -= 1
                if self._host_active_count[host] <= 0:
                    del self._host_active_count[host]
        self._stats['failed'] += 1
    
    def get_stats(self):
        """获取统计信息"""
        db_stats = self.db.get_queue_stats()
        return {
            **self._stats,
            'db_queue': db_stats,
            'heap_size': len(self._heap),
            'active_hosts': len(self._host_active_count),
        }
    
    def has_urls(self):
        """检查是否还有待爬取的 URL"""
        if len(self._heap) > 0:
            return True
        
        # 检查数据库队列
        db_stats = self.db.get_queue_stats()
        return db_stats.get('pending', 0) > 0
    
    def load_from_db(self):
        """从数据库加载待爬取的 URL 到内存队列"""
        # 获取所有 pending 状态的 URL
        with self._heap_lock:
            # 这里简化处理，实际生产环境应该分页加载
            pass
    
    def is_seen(self, url):
        """检查 URL 是否已见过"""
        url = normalize_url(url)
        with self._seen_lock:
            return url in self._seen_urls
