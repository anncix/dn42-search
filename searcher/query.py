# -*- coding: utf-8 -*-
"""
查询处理器
解析用户查询，进行查询理解、扩展、拼写检查
"""
import re
from utils.logger import get_logger
from indexer.tokenizer import Tokenizer
from searcher.spellcheck import SpellChecker

logger = get_logger('searcher.query')


class QueryParser:
    """查询解析器"""
    
    def __init__(self):
        self.tokenizer = Tokenizer()
        self.spellchecker = None
    
    def init_spellchecker(self, index):
        """从索引初始化拼写检查器"""
        terms = {}
        for term in index.get_all_terms():
            # 使用文档频率作为词频近似
            df = index.doc_frequency(term)
            terms[term] = df
        
        self.spellchecker = SpellChecker(terms)
        logger.info("拼写检查器已初始化")
    
    def parse(self, query_str):
        """
        解析查询字符串
        
        Args:
            query_str: 用户输入的查询字符串
        
        Returns:
            dict: 包含解析后的查询信息
        """
        result = {
            'original': query_str,
            'tokens': [],
            'terms': [],
            'phrases': [],
            'filters': {},
            'is_valid': True,
        }
        
        if not query_str or not query_str.strip():
            result['is_valid'] = False
            return result
        
        query_str = query_str.strip()
        
        # 提取短语（用引号括起来的部分）
        phrases = re.findall(r'"([^"]+)"', query_str)
        result['phrases'] = phrases
        
        # 移除短语，处理剩余部分
        remaining = re.sub(r'"[^"]+"', ' ', query_str)
        
        # 分词
        tokens = self.tokenizer.tokenize(remaining)
        result['tokens'] = tokens
        result['terms'] = list(set(tokens))  # 去重
        
        # 提取特殊操作符（如 site:, title: 等）
        result['filters'] = self._extract_filters(query_str)
        
        return result
    
    def _extract_filters(self, query_str):
        """提取查询过滤器"""
        filters = {}
        
        # site: 限定域名
        site_match = re.search(r'site:(\S+)', query_str)
        if site_match:
            filters['site'] = site_match.group(1)
        
        # title: 限定标题
        title_match = re.search(r'title:(\S+)', query_str)
        if title_match:
            filters['title'] = title_match.group(1)
        
        # filetype: 限定文件类型
        type_match = re.search(r'filetype:(\S+)', query_str)
        if type_match:
            filters['filetype'] = type_match.group(1)
        
        return filters
    
    def expand_query(self, query_terms, index, n=5):
        """
        查询扩展（伪相关反馈简化版）
        
        从高相关文档中提取扩展词
        """
        # 简化实现：返回相似词
        # 实际生产环境应该使用伪相关反馈或词向量
        expanded = list(query_terms)
        
        # 添加一些常见的相关词（基于词根）
        for term in query_terms:
            # 简单的词形变化扩展
            if len(term) > 4:
                if term.endswith('ing'):
                    expanded.append(term[:-3])
                elif term.endswith('ed'):
                    expanded.append(term[:-2])
                elif term.endswith('s'):
                    expanded.append(term[:-1])
                elif term.endswith('tion'):
                    expanded.append(term[:-4])
        
        return list(set(expanded))
    
    def correct_spelling(self, query_str):
        """
        拼写检查与修正
        
        Returns:
            tuple: (corrected_query, corrections, has_correction)
        """
        if not self.spellchecker:
            return query_str, [], False
        
        corrected_query, corrections = self.spellchecker.correct_query(query_str)
        has_correction = len(corrections) > 0
        
        return corrected_query, corrections, has_correction
    
    def classify_intent(self, query_str):
        """
        查询意图分类
        
        Returns:
            str: 'navigational' | 'informational' | 'transactional'
        """
        query_lower = query_str.lower()
        
        # 导航型：包含明确的网站/品牌名
        nav_indicators = ['wiki', 'homepage', 'official', 'site', '官网', '首页']
        if any(ind in query_lower for ind in nav_indicators):
            return 'navigational'
        
        # 事务型：包含动作词
        trans_indicators = ['download', 'buy', 'login', 'register', 'sign up',
                           '下载', '购买', '登录', '注册', '申请']
        if any(ind in query_lower for ind in trans_indicators):
            return 'transactional'
        
        # 默认：信息型
        return 'informational'
