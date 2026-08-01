# -*- coding: utf-8 -*-
"""
搜索引擎主服务
整合索引、排序、查询处理，提供统一的搜索接口
"""
import time
import re
from config import SEARCH_CONFIG, INDEX_CONFIG
from utils.logger import get_logger
from indexer.index import InvertedIndex
from indexer.builder import IndexBuilder
from ranker.ranker import Ranker
from ranker.pagerank import PageRankCalculator
from searcher.query import QueryParser
from searcher.spellcheck import SpellChecker
from storage.db import Database

logger = get_logger('searcher.engine')


class SearchEngine:
    """搜索引擎主类"""
    
    def __init__(self, db=None, index=None):
        self.db = db or Database()
        self.index = index or InvertedIndex()
        self.ranker = Ranker(self.index)
        self.query_parser = QueryParser()
        self.config = SEARCH_CONFIG
        
        # 索引是否已加载
        self._index_loaded = False
    
    def load_index(self):
        """加载索引"""
        success = self.index.load()
        if success:
            self._index_loaded = True
            # 初始化拼写检查器
            self.query_parser.init_spellchecker(self.index)
            logger.info("搜索引擎索引加载完成")
        else:
            logger.warning("索引加载失败，请先构建索引")
        return success
    
    def build_index(self):
        """从数据库构建索引"""
        builder = IndexBuilder(self.db, self.index)
        count = builder.build_from_database()
        
        if count > 0:
            self._index_loaded = True
            self.query_parser.init_spellchecker(self.index)
        
        return count
    
    def compute_pagerank(self):
        """计算 PageRank"""
        calculator = PageRankCalculator()
        pagerank = calculator.compute_from_db(self.db)
        
        # 更新索引中的 PageRank
        for doc_id, rank in pagerank.items():
            self.index.update_pagerank(doc_id, rank)
        
        # 重新保存索引
        self.index.save()
        
        return pagerank
    
    def search(self, query_str, limit=None, offset=0, mode='hybrid'):
        """
        执行搜索
        
        Args:
            query_str: 查询字符串
            limit: 返回结果数量
            offset: 偏移量
            mode: 排序模式
        
        Returns:
            dict: 搜索结果
        """
        start_time = time.time()
        
        if not self._index_loaded:
            return {
                'results': [],
                'total': 0,
                'error': '索引未加载',
                'time_ms': 0,
            }
        
        limit = limit or self.config['default_limit']
        limit = min(limit, self.config['max_limit'])
        
        result = {
            'query': query_str,
            'original_query': query_str,
            'results': [],
            'total': 0,
            'time_ms': 0,
            'page': offset // limit + 1,
            'page_size': limit,
            'suggestion': None,
            'corrections': [],
        }
        
        if not query_str or not query_str.strip():
            result['time_ms'] = int((time.time() - start_time) * 1000)
            return result
        
        # 拼写检查
        if self.config['enable_spellcheck']:
            corrected, corrections, has_correction = self.query_parser.correct_spelling(query_str)
            if has_correction:
                result['corrections'] = corrections
                result['suggestion'] = corrected
                # 使用修正后的查询进行搜索
                query_str = corrected
        
        result['query'] = query_str
        
        # 解析查询
        parsed = self.query_parser.parse(query_str)
        
        if not parsed['is_valid'] or not parsed['terms']:
            result['time_ms'] = int((time.time() - start_time) * 1000)
            return result
        
        terms = parsed['terms']
        
        # 执行排序
        ranked_results = self.ranker.rank(
            terms,
            mode=mode,
            limit=limit,
            offset=offset
        )
        
        # 生成结果详情
        search_results = []
        for doc_id, final_score, bm25_score, pr_score in ranked_results:
            doc_info = self.index.get_doc_info(doc_id)
            if not doc_info:
                continue
            
            # 生成摘要
            snippet = self._generate_snippet(doc_info, terms)
            
            search_results.append({
                'doc_id': doc_id,
                'url': doc_info.get('url', ''),
                'title': doc_info.get('title', doc_info.get('url', '无标题')),
                'snippet': snippet,
                'score': {
                    'final': round(final_score, 6),
                    'bm25': round(bm25_score, 4),
                    'pagerank': round(pr_score, 8),
                },
            })
        
        # 估算总数（简化为所有匹配数）
        total = self._count_matches(terms)
        
        result['results'] = search_results
        result['total'] = total
        result['time_ms'] = int((time.time() - start_time) * 1000)
        
        logger.debug(
            f"搜索: '{query_str}' -> {total} 结果, "
            f"耗时 {result['time_ms']}ms"
        )
        
        return result
    
    def _count_matches(self, terms):
        """
        计算匹配文档数（AND 语义：所有词项都必须出现）
        
        通过计算所有词项倒排列表的交集来得到准确匹配数。
        """
        if not terms:
            return 0
        
        # 获取所有词项的倒排列表文档 ID 集合
        postings_sets = []
        for term in terms:
            postings = self.index.get_postings(term)
            if not postings:
                # 任一词项不存在匹配文档，AND 结果为空
                return 0
            postings_sets.append(set(postings.keys()))
        
        # 计算交集（所有词项都出现的文档）
        result_set = postings_sets[0]
        for s in postings_sets[1:]:
            result_set = result_set & s
        
        return len(result_set)
    
    def _generate_snippet(self, doc_info, query_terms):
        """
        生成搜索结果摘要（高亮关键词）
        
        简化实现：从标题和 URL 中提取相关片段
        """
        snippet_length = self.config['snippet_length']
        
        # 优先使用标题
        title = doc_info.get('title', '')
        url = doc_info.get('url', '')
        
        # 构建摘要文本
        text = title + ' ' + url
        
        # 简单截取
        if len(text) > snippet_length:
            # 尝试找到第一个查询词的位置
            text_lower = text.lower()
            best_pos = 0
            
            for term in query_terms:
                pos = text_lower.find(term.lower())
                if pos >= 0:
                    best_pos = max(0, pos - 50)
                    break
            
            snippet = text[best_pos:best_pos + snippet_length]
            if best_pos > 0:
                snippet = '...' + snippet
            if best_pos + snippet_length < len(text):
                snippet = snippet + '...'
        else:
            snippet = text
        
        # 高亮查询词（用 <em> 标签）
        for term in query_terms:
            pattern = re.compile(re.escape(term), re.IGNORECASE)
            snippet = pattern.sub(f'<em>{term}</em>', snippet)
        
        return snippet
    
    def get_stats(self):
        """获取搜索引擎统计信息"""
        db_stats = self.db.get_index_status()
        index_stats = self.index.stats() if self._index_loaded else {}
        link_stats = self.db.get_link_stats()
        
        return {
            'index_loaded': self._index_loaded,
            'database': db_stats,
            'index': index_stats,
            'links': link_stats,
            'pages_crawled': self.db.get_page_count(),
        }
    
    def get_top_pages(self, n=10):
        """获取 PageRank 最高的页面"""
        pages = self.db.get_all_pages()
        ranked = sorted(pages, key=lambda p: p.get('pagerank', 0), reverse=True)
        return ranked[:n]
    
    def explain(self, query_str, doc_id):
        """解释文档的排序得分"""
        parsed = self.query_parser.parse(query_str)
        if not parsed['terms']:
            return None
        
        return self.ranker.explain(doc_id, parsed['terms'])
