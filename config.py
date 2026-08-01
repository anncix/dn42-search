# -*- coding: utf-8 -*-
"""
DN42 搜索引擎配置文件
"""
import os

# ========== 基础配置 ==========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
LOG_DIR = os.path.join(BASE_DIR, 'logs')

# 确保目录存在
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# ========== 爬虫配置 ==========
CRAWLER_CONFIG = {
    # 并发数
    'max_concurrent_requests': 50,
    
    # 每主机最大并发请求数（礼貌性）
    'max_per_host': 3,
    
    # 请求间隔（秒），同一主机的请求间隔
    'politeness_delay': 1.0,
    
    # 请求超时（秒）
    'request_timeout': 30,
    
    # 最大爬取深度（从种子URL算起）
    'max_depth': 10,
    
    # 最大页面大小（字节）- 10MB
    'max_page_size': 10 * 1024 * 1024,
    
    # User-Agent
    'user_agent': 'DN42SearchBot/1.0 (+https://wiki.dn42/search; bot@dn42.search)',
    
    # 重试次数
    'max_retries': 3,
    
    # 重试延迟（秒）
    'retry_delay': 5,
    
    # DNS 缓存大小
    'dns_cache_size': 10000,
    
    # 连接池大小
    'connection_pool_size': 100,
    
    # 是否遵循 robots.txt
    'respect_robots_txt': True,
    
    # robots.txt 缓存 TTL（秒）
    'robots_cache_ttl': 86400,  # 24小时
}

# ========== DN42 网络配置 ==========
DN42_CONFIG = {
    # IPv4 范围
    'ipv4_ranges': [
        '172.20.0.0/14',  # 主范围 172.20.0.0 - 172.23.255.255
    ],
    
    # IPv6 范围
    'ipv6_ranges': [
        'fd00::/8',  # ULA 范围（dn42 使用其中部分）
    ],
    
    # 允许的域名后缀
    'allowed_tlds': [
        '.dn42',
        '.dn42.dev',  # clearnet 镜像也允许
    ],
    
    # 种子 URL（初始爬取入口）
    'seed_urls': [
        'https://wiki.dn42/',
        'https://wiki.dn42.dev/',
        'https://explorer.burble.dn42/',
        'https://map.dn42/',
        'http://whois.dn42/',
        'https://baaka.dn42/',
        'https://discover.dn42/',
    ],
    
    # 内部服务域名（从 dn42 registry 发现）
    'internal_services': [
        'wiki.dn42',
        'whois.dn42',
        'collector.dn42',
        'lg.collector.dn42',
        'irc.dn42',
        'map.dn42',
        'explorer.burble.dn42',
        'baaka.dn42',
        'discover.dn42',
        'files.nop.dn42',
        'paste.nop.dn42',
        'speedtest.burble.dn42',
        'burble.dn42',
    ],
}

# ========== 索引配置 ==========
INDEX_CONFIG = {
    # 索引存储路径
    'index_path': os.path.join(DATA_DIR, 'index'),
    
    # 是否启用索引压缩
    'enable_compression': True,
    
    # 索引分段大小（文档数）
    'segment_size': 10000,
    
    # 内存缓冲区大小（文档数）- 满了刷新到磁盘
    'buffer_size': 5000,
    
    # BM25 参数
    'bm25_k1': 1.5,  # 词频饱和参数
    'bm25_b': 0.75,  # 文档长度归一化参数
    
    # 字段权重
    'field_weights': {
        'title': 5.0,
        'url': 3.0,
        'headings': 2.0,  # h1-h3
        'body': 1.0,
        'anchor': 2.5,  # 锚文本
    },
}

# ========== PageRank 配置 ==========
PAGERANK_CONFIG = {
    # 阻尼因子
    'damping_factor': 0.85,
    
    # 最大迭代次数
    'max_iterations': 100,
    
    # 收敛阈值
    'tolerance': 1e-6,
    
    # 计算周期（秒）
    'compute_interval': 3600,  # 每小时
}

# ========== 搜索配置 ==========
SEARCH_CONFIG = {
    # 默认返回结果数
    'default_limit': 20,
    
    # 最大返回结果数
    'max_limit': 100,
    
    # 是否启用拼写检查
    'enable_spellcheck': True,
    
    # 拼写检查最大编辑距离
    'spellcheck_max_edits': 2,
    
    # 是否启用查询扩展
    'enable_query_expansion': False,
    
    # 查询扩展词数量
    'query_expansion_terms': 5,
    
    # 高亮片段长度
    'snippet_length': 200,
    
    # 高亮片段数量
    'snippet_count': 3,
}

# ========== Web 服务配置 ==========
WEB_CONFIG = {
    'host': '0.0.0.0',
    'port': 8080,
    'debug': False,
    'secret_key': 'dn42-search-secret-key-change-in-production',
}

# ========== 数据库配置 ==========
DB_CONFIG = {
    'path': os.path.join(DATA_DIR, 'crawler.db'),
}

# ========== 日志配置 ==========
LOG_CONFIG = {
    'level': 'INFO',
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'file': os.path.join(LOG_DIR, 'dn42-search.log'),
    'max_bytes': 10 * 1024 * 1024,  # 10MB
    'backup_count': 5,
}
