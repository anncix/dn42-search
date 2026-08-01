# -*- coding: utf-8 -*-
"""
索引构建器
从数据库中读取页面数据，构建倒排索引
"""
import time
from utils.logger import get_logger
from indexer.index import InvertedIndex
from storage.db import Database

logger = get_logger('indexer.builder')


class IndexBuilder:
    """索引构建器"""
    
    def __init__(self, db=None, index=None):
        self.db = db or Database()
        self.index = index or InvertedIndex()
    
    def build_from_database(self, batch_size=1000):
        """
        从数据库构建索引
        
        Args:
            batch_size: 每批处理的文档数
        """
        logger.info("开始从数据库构建索引...")
        start_time = time.time()
        
        # 获取总页数
        total_pages = self.db.get_page_count()
        logger.info(f"总页数: {total_pages}")
        
        if total_pages == 0:
            logger.warning("数据库中没有页面数据")
            return 0
        
        # 清空现有索引
        self.index.clear()
        
        # 分批处理
        offset = 0
        processed = 0
        
        while offset < total_pages:
            pages = self.db.get_all_pages(limit=batch_size, offset=offset)
            
            for page in pages:
                # 从数据库获取完整文本（实际应用中应该单独存储）
                # 这里我们从 page 数据中构建索引字段
                fields = {
                    'url': page['url'],
                    'title': page['title'] or '',
                    'body': page.get('text', '') or '',  # 如果有 text 字段
                    # 从标题中提取 heading
                    'headings': page['title'] or '',
                }
                
                self.index.add_document(page['doc_id'], fields)
                processed += 1
                
                # 标记为已索引
                self.db.mark_page_indexed(page['doc_id'])
            
            offset += batch_size
            logger.info(f"已处理 {processed}/{total_pages} 页 ({processed/total_pages*100:.1f}%)")
        
        # 更新 PageRank
        self._update_pagerank_from_db()
        
        # 保存索引
        self.index.save()
        
        # 更新数据库中的索引状态
        self.db.update_index_status(
            total_docs=self.index.total_docs,
            total_terms=self.index.vocabulary_size
        )
        
        elapsed = time.time() - start_time
        stats = self.index.stats()
        logger.info(
            f"索引构建完成！耗时 {elapsed:.2f} 秒\n"
            f"  - 文档数: {stats['total_docs']}\n"
            f"  - 词项数: {stats['vocabulary_size']}\n"
            f"  - 倒排列表项: {stats['total_postings']}\n"
            f"  - 平均文档长度: {stats['avg_doc_length']:.1f}"
        )
        
        return processed
    
    def _update_pagerank_from_db(self):
        """从数据库更新 PageRank 到索引中"""
        pages = self.db.get_all_pages()
        for page in pages:
            if page.get('pagerank', 0) > 0:
                self.index.update_pagerank(page['doc_id'], page['pagerank'])
    
    def add_document(self, doc_id, fields):
        """添加单个文档到索引"""
        self.index.add_document(doc_id, fields)
        self.db.mark_page_indexed(doc_id)
    
    def incremental_update(self):
        """
        增量更新索引（添加新页面，更新已修改页面）
        
        实际生产环境中应该更精细地跟踪变化，
        这里简化为重建整个索引。
        """
        return self.build_from_database()
