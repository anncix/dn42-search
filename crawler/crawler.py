# -*- coding: utf-8 -*-
"""
分布式爬虫引擎
异步并发爬取 dn42 网络中的网页
"""
import asyncio
import time
import aiohttp
try:
    import aiodns
    HAS_AIODNS = True
except ImportError:
    HAS_AIODNS = False
from collections import defaultdict
from config import CRAWLER_CONFIG, DN42_CONFIG
from utils.logger import get_logger
from utils.url_utils import (
    normalize_url, get_domain, is_valid_url, is_allowed_domain,
    url_to_docid, RobotsTxtManager
)
from crawler.parser import PageParser
from crawler.frontier import URLFrontier
from storage.db import Database

logger = get_logger('crawler.engine')


class Crawler:
    """
    分布式爬虫引擎
    基于 aiohttp 实现异步并发爬取
    """
    
    def __init__(self, db=None):
        self.config = CRAWLER_CONFIG
        self.db = db or Database()
        self.parser = PageParser()
        self.frontier = URLFrontier(
            self.db,
            max_per_host=self.config['max_per_host'],
            politeness_delay=self.config['politeness_delay']
        )
        self.robots_manager = RobotsTxtManager(self.config['user_agent'])
        
        # 会话和 DNS 解析器
        self._session = None
        self._resolver = None
        
        # 运行状态
        self._running = False
        self._stats = {
            'pages_crawled': 0,
            'pages_failed': 0,
            'bytes_downloaded': 0,
            'start_time': None,
        }
    
    async def _init_session(self):
        """初始化 aiohttp 会话"""
        if self._session is None:
            # 创建 TCP 连接器
            connector_kwargs = dict(
                limit=self.config['max_concurrent_requests'],
                limit_per_host=self.config['max_per_host'],
                ttl_dns_cache=300,
                use_dns_cache=True,
            )
            
            # 可选：使用 aiodns 异步 DNS 解析
            if HAS_AIODNS:
                self._resolver = aiodns.DNSResolver()
                connector_kwargs['resolver'] = self._resolver
            
            connector = aiohttp.TCPConnector(**connector_kwargs)
            
            # 超时设置
            timeout = aiohttp.ClientTimeout(
                total=self.config['request_timeout'],
                connect=10,
                sock_read=20,
                sock_connect=10,
            )
            
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={
                    'User-Agent': self.config['user_agent'],
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5,zh-CN;q=0.3',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                }
            )
    
    async def _close_session(self):
        """关闭会话"""
        if self._session:
            await self._session.close()
            self._session = None
    
    async def fetch_page(self, url):
        """
        抓取单个页面
        
        Returns:
            dict: 页面数据，失败返回 None
        """
        try:
            async with self._session.get(url, allow_redirects=True) as response:
                # 检查状态码
                if response.status >= 400:
                    logger.debug(f"HTTP {response.status}: {url}")
                    return None
                
                # 检查内容类型
                content_type = response.headers.get('Content-Type', '')
                if 'text/html' not in content_type and 'text/plain' not in content_type:
                    # 只处理 HTML 和纯文本页面
                    return None
                
                # 检查内容大小
                content_length = response.headers.get('Content-Length')
                if content_length and int(content_length) > self.config['max_page_size']:
                    logger.debug(f"页面过大: {url}")
                    return None
                
                # 读取内容（限制大小）
                html = await response.text()
                
                if len(html.encode('utf-8')) > self.config['max_page_size']:
                    logger.debug(f"页面过大: {url}")
                    return None
                
                # 获取最后修改时间和 etag
                last_modified = response.headers.get('Last-Modified', '')
                etag = response.headers.get('ETag', '')
                
                # 获取最终 URL（跟随重定向后）
                final_url = str(response.url)
                
                return {
                    'url': final_url,
                    'html': html,
                    'status_code': response.status,
                    'content_type': content_type,
                    'content_length': len(html.encode('utf-8')),
                    'last_modified': last_modified,
                    'etag': etag,
                }
                
        except asyncio.TimeoutError:
            logger.debug(f"请求超时: {url}")
            return None
        except aiohttp.ClientError as e:
            logger.debug(f"请求错误: {url}, {e}")
            return None
        except Exception as e:
            logger.error(f"抓取页面异常: {url}, {e}")
            return None
    
    async def process_page(self, url, depth=0):
        """
        处理单个页面：抓取 -> 解析 -> 提取链接 -> 入队
        """
        # 检查 robots.txt
        if self.config['respect_robots_txt']:
            if not self.robots_manager.is_allowed(url):
                logger.debug(f"robots.txt 禁止爬取: {url}")
                self.frontier.mark_failed(url, retry=False)
                return None
        
        # 抓取页面
        page_data = await self.fetch_page(url)
        if not page_data:
            self.frontier.mark_failed(url, retry=True)
            self._stats['pages_failed'] += 1
            return None
        
        # 解析页面
        parsed = self.parser.parse(page_data['html'], page_data['url'])
        
        # 计算 doc_id
        doc_id = url_to_docid(page_data['url'])
        
        # 保存页面元数据
        page_info = {
            'url': page_data['url'],
            'doc_id': doc_id,
            'title': parsed['title'],
            'content_hash': parsed['content_hash'],
            'content_length': page_data['content_length'],
            'content_type': page_data['content_type'],
            'status_code': page_data['status_code'],
            'depth': depth,
            'last_modified': page_data['last_modified'],
            'etag': page_data['etag'],
            'text': parsed['text'],
            'headings': parsed['headings'],
            'meta_description': parsed['meta_description'],
        }
        
        self.db.save_page(page_info)
        self._stats['pages_crawled'] += 1
        self._stats['bytes_downloaded'] += page_data['content_length']
        
        # 保存链接关系
        links = [(link['url'], link['anchor']) for link in parsed['links']]
        self.db.add_links(doc_id, links)
        
        # 提取新 URL 并加入队列
        if depth < self.config['max_depth']:
            new_urls = []
            for link in parsed['links']:
                link_url = link['url']
                # 只处理允许域名范围内的 URL
                if is_valid_url(link_url) and is_allowed_domain(link_url):
                    if not self.frontier.is_seen(link_url):
                        new_urls.append(link_url)
            
            if new_urls:
                added = self.frontier.add_urls(new_urls, depth + 1, priority=5)
                logger.debug(f"发现 {len(new_urls)} 个新 URL，新增 {added} 个到队列")
        
        # 标记完成
        self.frontier.mark_completed(url)
        
        return page_info
    
    async def _worker(self, worker_id):
        """工作协程"""
        logger.info(f"Worker {worker_id} 启动")
        
        while self._running:
            # 获取下一个 URL
            url_info = self.frontier.get_next_url()
            
            if not url_info:
                # 没有 URL 了，等待一下
                await asyncio.sleep(0.5)
                continue
            
            url = url_info['url']
            depth = url_info.get('depth', 0)
            
            logger.debug(f"Worker {worker_id} 抓取: {url} (depth={depth})")
            
            try:
                await self.process_page(url, depth)
            except Exception as e:
                logger.error(f"Worker {worker_id} 处理页面出错: {url}, {e}")
                self.frontier.mark_failed(url, retry=False)
        
        logger.info(f"Worker {worker_id} 停止")
    
    async def _stats_reporter(self):
        """统计信息报告协程"""
        while self._running:
            await asyncio.sleep(10)  # 每 10 秒报告一次
            
            elapsed = time.time() - self._stats['start_time']
            rate = self._stats['pages_crawled'] / elapsed if elapsed > 0 else 0
            
            frontier_stats = self.frontier.get_stats()
            
            logger.info(
                f"[统计] 已抓取: {self._stats['pages_crawled']}, "
                f"失败: {self._stats['pages_failed']}, "
                f"速率: {rate:.2f} pages/s, "
                f"下载: {self._stats['bytes_downloaded'] / 1024 / 1024:.2f} MB, "
                f"队列: {frontier_stats['db_queue'].get('pending', 0)} pending"
            )
    
    async def crawl(self, seed_urls=None, max_pages=None, max_duration=None):
        """
        启动爬虫
        
        Args:
            seed_urls: 种子 URL 列表，默认使用配置中的
            max_pages: 最大抓取页数，None 表示不限制
            max_duration: 最大运行时间（秒），None 表示不限制
        """
        # 使用种子 URL
        seeds = seed_urls or DN42_CONFIG['seed_urls']
        
        # 添加种子 URL
        for url in seeds:
            if is_valid_url(url) and is_allowed_domain(url):
                self.frontier.add_url(url, depth=0, priority=1)
        
        logger.info(f"种子 URL 数量: {len(seeds)}")
        logger.info(f"开始爬取，并发数: {self.config['max_concurrent_requests']}")
        
        # 初始化会话
        await self._init_session()
        
        self._running = True
        self._stats['start_time'] = time.time()
        
        # 创建工作协程
        workers = []
        num_workers = min(self.config['max_concurrent_requests'], 20)
        for i in range(num_workers):
            worker = asyncio.create_task(self._worker(i))
            workers.append(worker)
        
        # 启动统计报告
        stats_task = asyncio.create_task(self._stats_reporter())
        
        try:
            # 等待完成条件
            start_time = time.time()
            while self._running:
                # 检查是否达到最大页数
                if max_pages and self._stats['pages_crawled'] >= max_pages:
                    logger.info(f"达到最大抓取页数: {max_pages}")
                    break
                
                # 检查是否达到最大运行时间
                if max_duration and (time.time() - start_time) >= max_duration:
                    logger.info(f"达到最大运行时间: {max_duration}s")
                    break
                
                # 检查是否还有 URL
                if not self.frontier.has_urls():
                    # 等待一会儿，看看是否有新 URL 加入
                    await asyncio.sleep(2)
                    if not self.frontier.has_urls():
                        logger.info("没有更多待爬取的 URL 了")
                        break
                
                await asyncio.sleep(1)
        
        except KeyboardInterrupt:
            logger.info("收到中断信号，停止爬虫")
        finally:
            self._running = False
            
            # 等待工作协程结束
            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            
            stats_task.cancel()
            await stats_task
            
            # 关闭会话
            await self._close_session()
        
        elapsed = time.time() - self._stats['start_time']
        avg_rate = self._stats['pages_crawled'] / elapsed if elapsed > 0 else 0
        logger.info(
            f"爬取结束。共抓取 {self._stats['pages_crawled']} 个页面，"
            f"失败 {self._stats['pages_failed']} 个，"
            f"耗时 {elapsed:.2f} 秒，"
            f"平均速率 {avg_rate:.2f} pages/s"
        )
        
        return self._stats
    
    def get_stats(self):
        """获取当前统计信息"""
        return {
            **self._stats,
            'frontier': self.frontier.get_stats(),
        }
    
    def close(self):
        """关闭资源"""
        self.db.close()
