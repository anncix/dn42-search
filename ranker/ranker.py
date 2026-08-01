# -*- coding: utf-8 -*-
"""
综合排序器
结合 BM25 相关性得分和 PageRank 权威度得分
"""
import math
from config import INDEX_CONFIG
from utils.logger import get_logger
from ranker.bm25 import BM25Scorer
from ranker.pagerank import PageRankCalculator

logger = get_logger('ranker.ranker')


class Ranker:
    """
    综合排序器
    
    排序公式：
    final_score = bm25_weight * normalized_bm25 + pagerank_weight * normalized_pagerank
    
    可配置多种排序模式：
    - relevance: 仅 BM25 相关性
    - authority: 仅 PageRank 权威度
    - hybrid: 混合模式（默认）
    - fresh: 新鲜度优先（需要时间数据）
    """
    
    def __init__(self, index, bm25_weight=0.7, pagerank_weight=0.3):
        self.index = index
        self.bm25_scorer = BM25Scorer(index)
        self.pagerank_weight = pagerank_weight
        self.bm25_weight = bm25_weight
    
    def rank(self, query_terms, doc_ids=None, mode='hybrid', limit=20, offset=0):
        """
        对文档进行排序
        
        Args:
            query_terms: 查询词项列表
            doc_ids: 待排序的文档 ID 列表（None 表示所有匹配文档）
            mode: 排序模式 ('relevance', 'authority', 'hybrid')
            limit: 返回结果数量
            offset: 偏移量
        
        Returns:
            list: [(doc_id, final_score, bm25_score, pagerank_score)]
        """
        # 获取 BM25 得分
        if doc_ids is None:
            bm25_scores = dict(self.bm25_scorer.score_all_matches(query_terms))
            doc_ids = list(bm25_scores.keys())
        else:
            bm25_scores = self.bm25_scorer.score_documents(doc_ids, query_terms)
        
        if not doc_ids:
            return []
        
        # 获取 PageRank 得分
        pagerank_scores = {}
        for doc_id in doc_ids:
            doc_info = self.index.get_doc_info(doc_id)
            pagerank_scores[doc_id] = doc_info.get('pagerank', 0) if doc_info else 0
        
        # 归一化得分（0-1 范围）
        max_bm25 = max(bm25_scores.values()) if bm25_scores else 1
        max_pr = max(pagerank_scores.values()) if pagerank_scores else 1
        
        if max_bm25 == 0:
            max_bm25 = 1
        if max_pr == 0:
            max_pr = 1
        
        # 计算综合得分
        final_scores = []
        
        for doc_id in doc_ids:
            bm25_norm = bm25_scores.get(doc_id, 0) / max_bm25
            pr_norm = pagerank_scores.get(doc_id, 0) / max_pr
            
            if mode == 'relevance':
                final = bm25_norm
            elif mode == 'authority':
                final = pr_norm
            elif mode == 'hybrid':
                final = (self.bm25_weight * bm25_norm + 
                        self.pagerank_weight * pr_norm)
            else:
                final = bm25_norm
            
            final_scores.append((
                doc_id,
                final,
                bm25_scores.get(doc_id, 0),
                pagerank_scores.get(doc_id, 0),
            ))
        
        # 排序
        final_scores.sort(key=lambda x: x[1], reverse=True)
        
        # 分页
        return final_scores[offset:offset + limit]
    
    def get_result_details(self, doc_id, query_terms):
        """获取结果详情（用于生成摘要和高亮）"""
        doc_info = self.index.get_doc_info(doc_id)
        if not doc_info:
            return None
        
        bm25_score = self.bm25_scorer.score_document(doc_id, query_terms)
        
        return {
            'doc_id': doc_id,
            'url': doc_info.get('url', ''),
            'title': doc_info.get('title', ''),
            'length': doc_info.get('length', 0),
            'pagerank': doc_info.get('pagerank', 0),
            'bm25_score': bm25_score,
        }
    
    def explain(self, doc_id, query_terms):
        """
        解释排序得分（调试用）
        
        返回每个查询词对得分的贡献
        """
        explanation = {
            'doc_id': doc_id,
            'query_terms': query_terms,
            'term_contributions': [],
            'total_bm25': 0,
            'pagerank': 0,
            'final_score': 0,
        }
        
        doc_info = self.index.get_doc_info(doc_id)
        if not doc_info:
            return explanation
        
        doc_length = doc_info['length']
        avgdl = self.index.avg_doc_length or 1
        N = self.index.total_docs
        
        total_bm25 = 0
        
        for term in query_terms:
            postings = self.index.get_postings(term)
            
            if doc_id not in postings:
                explanation['term_contributions'].append({
                    'term': term,
                    'tf': 0,
                    'idf': 0,
                    'contribution': 0,
                })
                continue
            
            tf = postings[doc_id]['freq']
            df = self.index.doc_frequency(term)
            idf = math.log((N - df + 0.5) / (df + 0.5) + 1) if df > 0 else 0
            
            # BM25 项得分
            k1 = self.bm25_scorer.k1
            b = self.bm25_scorer.b
            
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * doc_length / avgdl)
            contribution = idf * numerator / denominator
            
            total_bm25 += contribution
            
            explanation['term_contributions'].append({
                'term': term,
                'tf': tf,
                'df': df,
                'idf': round(idf, 4),
                'doc_length': doc_length,
                'avgdl': round(avgdl, 1),
                'contribution': round(contribution, 4),
            })
        
        explanation['total_bm25'] = round(total_bm25, 4)
        explanation['pagerank'] = doc_info.get('pagerank', 0)
        explanation['final_score'] = round(
            self.bm25_weight * (total_bm25 / max(total_bm25, 1)) + 
            self.pagerank_weight * (explanation['pagerank'] / max(explanation['pagerank'], 1)),
            4
        )
        
        return explanation
