# -*- coding: utf-8 -*-
"""
URL 工具函数
"""
import hashlib
import re
from urllib.parse import urlparse, urljoin, urlunparse, urldefrag
from urllib.robotparser import RobotFileParser
import ipaddress
from config import DN42_CONFIG


def normalize_url(url):
    """
    URL 规范化
    - 移除 fragment
    - 统一小写 scheme 和 host
    - 移除默认端口
    - 规范化路径
    """
    if not url:
        return url
    
    # 移除 fragment
    url, _ = urldefrag(url)
    
    try:
        parsed = urlparse(url)
    except ValueError:
        return url
    
    # 小写 scheme 和 host
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    
    # 移除默认端口
    if scheme == 'http' and netloc.endswith(':80'):
        netloc = netloc[:-3]
    elif scheme == 'https' and netloc.endswith(':443'):
        netloc = netloc[:-4]
    
    # 规范化路径（移除末尾多余斜杠，但保留根路径）
    path = parsed.path
    if path and path != '/' and path.endswith('/'):
        # 检查是否为重定向友好的路径，保留原样
        pass
    
    # 移除多余的斜杠
    path = re.sub(r'/+', '/', path)
    
    # 重建 URL
    normalized = urlunparse((
        scheme,
        netloc,
        path,
        parsed.params,
        parsed.query,
        ''  # 移除 fragment
    ))
    
    return normalized


def get_domain(url):
    """获取 URL 的域名"""
    try:
        parsed = urlparse(url)
        return parsed.netloc.split(':')[0].lower()
    except (ValueError, IndexError):
        return ''


def get_host(url):
    """获取 URL 的主机（含端口）"""
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower()
    except ValueError:
        return ''


def url_to_docid(url):
    """将 URL 转换为文档 ID（SHA-256 哈希）"""
    normalized = normalize_url(url)
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:32]


def is_allowed_domain(url):
    """检查 URL 是否属于允许的域名范围（dn42 内部）"""
    domain = get_domain(url)
    if not domain:
        return False
    
    # 检查是否为 .dn42 域名
    for tld in DN42_CONFIG['allowed_tlds']:
        if domain.endswith(tld) or domain == tld.lstrip('.'):
            return True
    
    # 检查 IP 是否在 dn42 范围内
    try:
        ip = ipaddress.ip_address(domain)
        for ip_range in DN42_CONFIG['ipv4_ranges'] + DN42_CONFIG['ipv6_ranges']:
            network = ipaddress.ip_network(ip_range, strict=False)
            if ip in network:
                return True
    except ValueError:
        # 不是 IP 地址
        pass
    
    return False


def is_valid_url(url):
    """检查 URL 是否有效"""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ('http', 'https') and bool(parsed.netloc)
    except ValueError:
        return False


def resolve_url(base_url, relative_url):
    """解析相对 URL 为绝对 URL"""
    try:
        return urljoin(base_url, relative_url)
    except ValueError:
        return None


def is_same_domain(url1, url2):
    """检查两个 URL 是否同域名"""
    return get_domain(url1) == get_domain(url2)


def get_url_depth(url, base_url):
    """计算 URL 相对于 base_url 的深度"""
    try:
        parsed_url = urlparse(url)
        parsed_base = urlparse(base_url)
        
        # 不同域名返回 -1
        if parsed_url.netloc != parsed_base.netloc:
            return -1
        
        # 计算路径深度
        path = parsed_url.path.rstrip('/')
        if not path:
            return 0
        
        return path.count('/')
    except ValueError:
        return -1


class RobotsTxtManager:
    """robots.txt 管理器"""
    
    def __init__(self, user_agent):
        self.user_agent = user_agent
        self._parsers = {}  # domain -> (parser, timestamp)
        self._cache_ttl = 86400  # 24小时
    
    def is_allowed(self, url):
        """检查 URL 是否允许爬取"""
        domain = get_domain(url)
        if not domain:
            return True
        
        import time
        now = time.time()
        
        # 检查缓存
        if domain in self._parsers:
            parser, timestamp = self._parsers[domain]
            if now - timestamp < self._cache_ttl:
                return parser.can_fetch(self.user_agent, url)
        
        # 解析 robots.txt
        try:
            parser = RobotFileParser()
            robots_url = f"{urlparse(url).scheme}://{domain}/robots.txt"
            parser.set_url(robots_url)
            parser.read()
            self._parsers[domain] = (parser, now)
            return parser.can_fetch(self.user_agent, url)
        except Exception:
            # 获取失败时保守处理：允许爬取
            self._parsers[domain] = (_AlwaysAllowParser(), now)
            return True
    
    def get_crawl_delay(self, url):
        """获取爬取延迟（秒）"""
        domain = get_domain(url)
        if domain in self._parsers:
            parser, _ = self._parsers[domain]
            try:
                delay = parser.crawl_delay(self.user_agent)
                if delay:
                    return float(delay)
            except Exception:
                pass
        return None


class _AlwaysAllowParser:
    """始终允许的 parser（获取失败时使用）"""
    def can_fetch(self, user_agent, url):
        return True
    
    def crawl_delay(self, user_agent):
        return None
