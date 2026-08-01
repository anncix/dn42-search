# -*- coding: utf-8 -*-
"""
SQLite 数据库存储层
存储爬虫状态、页面元数据、链接关系等
"""
import sqlite3
import time
import hashlib
from contextlib import contextmanager
from config import DB_CONFIG
from utils.logger import get_logger

logger = get_logger('storage.db')


class Database:
    """数据库管理类"""
    
    def __init__(self, db_path=None):
        self.db_path = db_path or DB_CONFIG['path']
        self._conn = None
        self._init_db()
    
    @contextmanager
    def _get_cursor(self):
        """获取游标上下文"""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute('PRAGMA journal_mode=WAL')
            self._conn.execute('PRAGMA synchronous=NORMAL')
            self._conn.execute('PRAGMA cache_size=-10000')
        cursor = self._conn.cursor()
        try:
            yield cursor
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cursor.close()
    
    def _init_db(self):
        """初始化数据库表"""
        with self._get_cursor() as c:
            # 页面表
            c.execute('''
                CREATE TABLE IF NOT EXISTS pages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    doc_id TEXT UNIQUE NOT NULL,
                    domain TEXT,
                    title TEXT,
                    content_hash TEXT,
                    content_length INTEGER,
                    content_type TEXT,
                    status_code INTEGER,
                    depth INTEGER,
                    last_crawled_at REAL,
                    last_modified TEXT,
                    etag TEXT,
                    is_indexed INTEGER DEFAULT 0,
                    pagerank REAL DEFAULT 0.0,
                    created_at REAL,
                    updated_at REAL
                )
            ''')

            # 兼容旧数据库：如果缺少新列则自动添加
            c.execute("PRAGMA table_info(pages)")
            existing_cols = {row['name'] for row in c.fetchall()}
            new_cols = {
                'text': 'TEXT',
                'headings': 'TEXT',
                'meta_description': 'TEXT',
            }
            for col_name, col_type in new_cols.items():
                if col_name not in existing_cols:
                    c.execute(f'ALTER TABLE pages ADD COLUMN {col_name} {col_type}')
            
            # URL 队列表
            c.execute('''
                CREATE TABLE IF NOT EXISTS url_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    doc_id TEXT,
                    domain TEXT,
                    depth INTEGER DEFAULT 0,
                    priority INTEGER DEFAULT 5,
                    status TEXT DEFAULT 'pending',
                    retries INTEGER DEFAULT 0,
                    last_attempt_at REAL,
                    created_at REAL,
                    next_attempt_at REAL
                )
            ''')
            
            # 链接关系表（用于 PageRank）
            c.execute('''
                CREATE TABLE IF NOT EXISTS links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_doc_id TEXT NOT NULL,
                    to_url TEXT NOT NULL,
                    to_doc_id TEXT,
                    anchor_text TEXT,
                    created_at REAL,
                    UNIQUE(from_doc_id, to_url)
                )
            ''')
            
            # 索引状态表
            c.execute('''
                CREATE TABLE IF NOT EXISTS index_status (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    last_indexed_at REAL,
                    total_docs INTEGER DEFAULT 0,
                    total_terms INTEGER DEFAULT 0,
                    version INTEGER DEFAULT 1
                )
            ''')
            
            # 创建索引
            c.execute('CREATE INDEX IF NOT EXISTS idx_pages_domain ON pages(domain)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_pages_doc_id ON pages(doc_id)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_queue_status ON url_queue(status)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_queue_domain ON url_queue(domain)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_links_from ON links(from_doc_id)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_links_to ON links(to_doc_id)')
    
    # ========== URL 队列操作 ==========
    
    def add_url(self, url, depth=0, priority=5):
        """添加 URL 到队列"""
        from utils.url_utils import url_to_docid, get_domain, normalize_url
        
        url = normalize_url(url)
        doc_id = url_to_docid(url)
        domain = get_domain(url)
        now = time.time()
        
        try:
            with self._get_cursor() as c:
                c.execute('''
                    INSERT OR IGNORE INTO url_queue 
                    (url, doc_id, domain, depth, priority, status, created_at, next_attempt_at)
                    VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
                ''', (url, doc_id, domain, depth, priority, now, now))
                return c.rowcount > 0
        except Exception as e:
            logger.error(f"添加 URL 失败: {url}, {e}")
            return False
    
    def add_urls(self, urls, depth=0, priority=5):
        """批量添加 URL"""
        count = 0
        for url in urls:
            if self.add_url(url, depth, priority):
                count += 1
        return count
    
    def get_next_url(self, domain=None):
        """获取下一个待爬取的 URL"""
        with self._get_cursor() as c:
            now = time.time()
            if domain:
                c.execute('''
                    SELECT id, url, doc_id, depth, retries 
                    FROM url_queue 
                    WHERE status = 'pending' AND domain = ? AND next_attempt_at <= ?
                    ORDER BY priority ASC, depth ASC, created_at ASC
                    LIMIT 1
                ''', (domain, now))
            else:
                c.execute('''
                    SELECT id, url, doc_id, depth, retries 
                    FROM url_queue 
                    WHERE status = 'pending' AND next_attempt_at <= ?
                    ORDER BY priority ASC, depth ASC, created_at ASC
                    LIMIT 1
                ''', (now,))
            
            row = c.fetchone()
            if row:
                # 标记为抓取中
                c.execute('''
                    UPDATE url_queue 
                    SET status = 'crawling', last_attempt_at = ?
                    WHERE id = ?
                ''', (now, row['id']))
                return dict(row)
            return None
    
    def mark_url_success(self, url, doc_id=None):
        """标记 URL 抓取成功"""
        with self._get_cursor() as c:
            c.execute('''
                UPDATE url_queue SET status = 'completed' WHERE url = ?
            ''', (url,))
    
    def mark_url_failed(self, url, retry=False):
        """标记 URL 抓取失败"""
        with self._get_cursor() as c:
            now = time.time()
            if retry:
                c.execute('''
                    UPDATE url_queue 
                    SET status = 'pending', retries = retries + 1, 
                        next_attempt_at = ? + (retries + 1) * 300
                    WHERE url = ?
                ''', (now, url))
            else:
                c.execute('''
                    UPDATE url_queue SET status = 'failed', retries = retries + 1
                    WHERE url = ?
                ''', (url,))
    
    def get_queue_stats(self):
        """获取队列统计信息"""
        with self._get_cursor() as c:
            c.execute('''
                SELECT status, COUNT(*) as count 
                FROM url_queue 
                GROUP BY status
            ''')
            rows = c.fetchall()
            return {row['status']: row['count'] for row in rows}
    
    def url_exists(self, url):
        """检查 URL 是否已存在（队列或已完成）"""
        from utils.url_utils import normalize_url
        url = normalize_url(url)
        
        with self._get_cursor() as c:
            c.execute('SELECT 1 FROM url_queue WHERE url = ? LIMIT 1', (url,))
            if c.fetchone():
                return True
            c.execute('SELECT 1 FROM pages WHERE url = ? LIMIT 1', (url,))
            return c.fetchone() is not None
    
    # ========== 页面操作 ==========
    
    def save_page(self, page_data):
        """保存页面数据"""
        from utils.url_utils import url_to_docid, get_domain, normalize_url
        
        url = normalize_url(page_data['url'])
        doc_id = page_data.get('doc_id') or url_to_docid(url)
        domain = get_domain(url)
        now = time.time()
        
        with self._get_cursor() as c:
            c.execute('''
                INSERT OR REPLACE INTO pages 
                (url, doc_id, domain, title, content_hash, content_length,
                 content_type, status_code, depth, last_crawled_at, 
                 last_modified, etag, text, headings, meta_description,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
                        COALESCE((SELECT created_at FROM pages WHERE url = ?), ?), ?)
            ''', (
                url, doc_id, domain,
                page_data.get('title', ''),
                page_data.get('content_hash', ''),
                page_data.get('content_length', 0),
                page_data.get('content_type', ''),
                page_data.get('status_code', 200),
                page_data.get('depth', 0),
                now,
                page_data.get('last_modified', ''),
                page_data.get('etag', ''),
                page_data.get('text', ''),
                page_data.get('headings', ''),
                page_data.get('meta_description', ''),
                url, now, now
            ))
    
    def get_page(self, url=None, doc_id=None):
        """获取页面信息"""
        with self._get_cursor() as c:
            if url:
                c.execute('SELECT * FROM pages WHERE url = ?', (url,))
            elif doc_id:
                c.execute('SELECT * FROM pages WHERE doc_id = ?', (doc_id,))
            else:
                return None
            row = c.fetchone()
            return dict(row) if row else None
    
    def get_all_pages(self, limit=None, offset=0):
        """获取所有页面"""
        with self._get_cursor() as c:
            if limit:
                c.execute('SELECT * FROM pages ORDER BY id LIMIT ? OFFSET ?', (limit, offset))
            else:
                c.execute('SELECT * FROM pages ORDER BY id')
            return [dict(row) for row in c.fetchall()]
    
    def get_page_count(self):
        """获取页面总数"""
        with self._get_cursor() as c:
            c.execute('SELECT COUNT(*) as cnt FROM pages')
            return c.fetchone()['cnt']
    
    def update_page_pagerank(self, doc_id, pagerank):
        """更新页面的 PageRank 值"""
        with self._get_cursor() as c:
            c.execute('''
                UPDATE pages SET pagerank = ? WHERE doc_id = ?
            ''', (pagerank, doc_id))
    
    def mark_page_indexed(self, doc_id):
        """标记页面已索引"""
        with self._get_cursor() as c:
            c.execute('''
                UPDATE pages SET is_indexed = 1 WHERE doc_id = ?
            ''', (doc_id,))
    
    # ========== 链接关系操作 ==========
    
    def add_links(self, from_doc_id, links):
        """添加链接关系
        
        Args:
            from_doc_id: 源文档 ID
            links: 列表，每项为 (to_url, anchor_text)
        """
        from utils.url_utils import url_to_docid, normalize_url
        now = time.time()
        
        with self._get_cursor() as c:
            for to_url, anchor_text in links:
                to_url = normalize_url(to_url)
                to_doc_id = url_to_docid(to_url)
                try:
                    c.execute('''
                        INSERT OR IGNORE INTO links 
                        (from_doc_id, to_url, to_doc_id, anchor_text, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (from_doc_id, to_url, to_doc_id, anchor_text, now))
                except Exception:
                    pass
    
    def get_outgoing_links(self, doc_id):
        """获取页面的出链"""
        with self._get_cursor() as c:
            c.execute('''
                SELECT to_url, to_doc_id, anchor_text 
                FROM links WHERE from_doc_id = ?
            ''', (doc_id,))
            return [dict(row) for row in c.fetchall()]
    
    def get_incoming_links(self, doc_id):
        """获取页面的入链"""
        with self._get_cursor() as c:
            c.execute('''
                SELECT from_doc_id, anchor_text 
                FROM links WHERE to_doc_id = ?
            ''', (doc_id,))
            return [dict(row) for row in c.fetchall()]
    
    def get_all_links(self):
        """获取所有链接关系（用于 PageRank 计算）"""
        with self._get_cursor() as c:
            c.execute('SELECT from_doc_id, to_doc_id FROM links WHERE to_doc_id IS NOT NULL')
            return [(row['from_doc_id'], row['to_doc_id']) for row in c.fetchall()]
    
    def get_link_stats(self):
        """获取链接统计"""
        with self._get_cursor() as c:
            c.execute('SELECT COUNT(*) as cnt FROM links')
            total = c.fetchone()['cnt']
            c.execute('SELECT COUNT(DISTINCT from_doc_id) as cnt FROM links')
            from_count = c.fetchone()['cnt']
            c.execute('SELECT COUNT(DISTINCT to_doc_id) as cnt FROM links WHERE to_doc_id IS NOT NULL')
            to_count = c.fetchone()['cnt']
            return {
                'total': total,
                'unique_from': from_count,
                'unique_to': to_count
            }
    
    # ========== 索引状态操作 ==========
    
    def get_index_status(self):
        """获取索引状态"""
        with self._get_cursor() as c:
            c.execute('SELECT * FROM index_status WHERE id = 1')
            row = c.fetchone()
            if not row:
                c.execute('INSERT INTO index_status (id) VALUES (1)')
                return {'id': 1, 'last_indexed_at': None, 'total_docs': 0, 'total_terms': 0, 'version': 1}
            return dict(row)
    
    def update_index_status(self, total_docs=None, total_terms=None):
        """更新索引状态"""
        with self._get_cursor() as c:
            now = time.time()
            if total_docs is not None and total_terms is not None:
                c.execute('''
                    UPDATE index_status 
                    SET last_indexed_at = ?, total_docs = ?, total_terms = ?, version = version + 1
                    WHERE id = 1
                ''', (now, total_docs, total_terms))
            elif total_docs is not None:
                c.execute('''
                    UPDATE index_status 
                    SET last_indexed_at = ?, total_docs = ?, version = version + 1
                    WHERE id = 1
                ''', (now, total_docs))
    
    def close(self):
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None
