# -*- coding: utf-8 -*-
"""
BM25 排序算法实现

BM25 (Best Matching 25) 是概率检索模型的经典算法，
在 TF-IDF 基础上增加了词频饱和和文档长度归一化。

公式：
Score(D, Q) = Σ IDF(q_i) * (f(q_i, D) * (k1 + 1)) / (f(q_i, D) + k1 * (1 - b + b * |D| / avgdl))

其中：
- IDF(q_i): 逆文档频率
- f(q_i, D): 词项在文档中的频率
- |D|: 文档长度
- avgdl: 平均文档长度
- k1: 词频饱和参数（通常 1.2-2.0）
- b: 文档长度归一化参数（通常 0.75）
"""
import math
from config import INDEX_CONFIG
from utils.logger import get_logger

logger = get_logger('ranker.bm25')


class BM25Scorer:
    """BM25 评分器"""
    
    def __init__(self, index, k1=None, b=None):
        self.index = index
        self.k1 = k1 or INDEX_CONFIG['bm25_k1']
        self.b = b or INDEX_CONFIG['bm25_b']
    
    def idf(self, term):
        """
        计算逆文档频率（Robertson/Sparck Jones 形式）
        
        IDF(q_i) = ln((N - df(q_i) + 0.5) / (df(q_i) + 0.5) + 1)
        """
        N = self.index.total_docs
        df = self.index.doc_frequency(term)
        
        if df == 0:
            return 0.0
        
        # 平滑处理，避免 df=0 或 df=N 时的数值不稳定
        idf = math.log((N - df + 0.5) / (df + 0.5) + 1)
        
        return max(0, idf)  # 确保非负
    
    def score_document(self, doc_id, query_terms):
        """
        计算文档对查询的 BM25 得分
        
        Args:
            doc_id: 文档 ID
            query_terms: 查询词项列表
        
        Returns:
            float: BM25 得分
        """
        score = 0.0
        doc_info = self.index.get_doc_info(doc_id)
        
        if not doc_info:
            return 0.0
        
        doc_length = doc_info['length']
        avgdl = self.index.avg_doc_length
        
        if avgdl == 0:
            avgdl = 1
        
        for term in query_terms:
            postings = self.index.get_postings(term)
            
            if doc_id not in postings:
                continue
            
            tf = postings[doc_id]['freq']
            idf = self.idf(term)
            
            # BM25 核心公式
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * doc_length / avgdl)
            
            score += idf * numerator / denominator
        
        return score
    
    def score_documents(self, doc_ids, query_terms):
        """
        批量计算文档得分
        
        Returns:
            dict: {doc_id: score}
        """
        scores = {}
        
        for doc_id in doc_ids:
            scores[doc_id] = self.score_document(doc_id, query_terms)
        
        return scores
    
    def score_all_matches(self, query_terms):
        """
        计算所有匹配文档的得分
        
        Returns:
            list: [(doc_id, score)] 按得分降序排列
        """
        # 获取所有匹配文档的并集
        matched_docs = set()
        for term in query_terms:
            postings = self.index.get_postings(term)
            matched_docs.update(postings.keys())
        
        if not matched_docs:
            return []
        
        # 计算得分
        scores = self.score_documents(matched_docs, query_terms)
        
        # 排序
        sorted_docs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        return sorted_docs
