# -*- coding: utf-8 -*-
"""
拼写检查器
基于编辑距离和语言模型概率的拼写纠正
"""
import re
from collections import Counter
from utils.logger import get_logger

logger = get_logger('searcher.spellcheck')


class SpellChecker:
    """
    拼写检查器
    
    使用 Peter Norvig 经典的拼写检查算法：
    - 基于编辑距离生成候选词
    - 基于词频语言模型选择最可能的修正
    """
    
    def __init__(self, dictionary_terms=None):
        """
        初始化拼写检查器
        
        Args:
            dictionary_terms: 词典词项及其频率，dict 形式 {term: freq}
        """
        self._word_freq = Counter()
        self._total_words = 0
        
        if dictionary_terms:
            self.load_dictionary(dictionary_terms)
    
    def load_dictionary(self, terms):
        """
        加载词典
        
        Args:
            terms: {term: frequency} 或 [terms] 列表
        """
        if isinstance(terms, dict):
            self._word_freq = Counter(terms)
        elif isinstance(terms, (list, set)):
            self._word_freq = Counter(terms)
        
        self._total_words = sum(self._word_freq.values())
        logger.info(f"拼写检查器已加载 {len(self._word_freq)} 个词")
    
    def add_word(self, word, freq=1):
        """添加词到词典"""
        word = word.lower()
        self._word_freq[word] += freq
        self._total_words += freq
    
    def probability(self, word):
        """计算词的概率"""
        if self._total_words == 0:
            return 0
        return self._word_freq.get(word.lower(), 0) / self._total_words
    
    def known(self, words):
        """返回已知的词（在词典中）"""
        return set(w for w in words if w.lower() in self._word_freq)
    
    def edits1(self, word):
        """
        生成所有编辑距离为 1 的词
        
        编辑操作：删除、交换、替换、插入
        """
        letters = 'abcdefghijklmnopqrstuvwxyz'
        word = word.lower()
        
        splits = [(word[:i], word[i:]) for i in range(len(word) + 1)]
        
        deletes = [L + R[1:] for L, R in splits if R]
        transposes = [L + R[1] + R[0] + R[2:] for L, R in splits if len(R) > 1]
        replaces = [L + c + R[1:] for L, R in splits if R for c in letters]
        inserts = [L + c + R for L, R in splits for c in letters]
        
        return set(deletes + transposes + replaces + inserts)
    
    def edits2(self, word):
        """生成所有编辑距离为 2 的词"""
        return set(
            e2 for e1 in self.edits1(word)
            for e2 in self.edits1(e1)
        )
    
    def candidates(self, word, max_edits=2):
        """
        获取候选修正词
        
        优先级：原词 > 编辑距离1 > 编辑距离2
        """
        word_lower = word.lower()
        
        # 原词如果在词典中，直接返回
        if word_lower in self._word_freq:
            return [word_lower]
        
        # 编辑距离 1
        candidates_1 = self.known(self.edits1(word))
        if candidates_1:
            return list(candidates_1)
        
        # 编辑距离 2
        if max_edits >= 2:
            candidates_2 = self.known(self.edits2(word))
            if candidates_2:
                return list(candidates_2)
        
        # 没有候选，返回原词
        return [word_lower]
    
    def correction(self, word, max_edits=2):
        """
        返回最可能的拼写修正
        
        Args:
            word: 待检查的词
            max_edits: 最大编辑距离
        
        Returns:
            str: 修正后的词
        """
        candidates = self.candidates(word, max_edits)
        if not candidates:
            return word
        
        # 选择概率最高的候选
        return max(candidates, key=self.probability)
    
    def correct_query(self, query, max_edits=2):
        """
        修正整个查询
        
        Args:
            query: 查询字符串
        
        Returns:
            tuple: (corrected_query, [corrections])
            corrections: [(original, corrected)]
        """
        words = re.findall(r'\b[a-zA-Z]+\b', query)
        if not words:
            return query, []
        
        corrections = []
        corrected_words = []
        
        for word in words:
            if len(word) < 3:  # 短词不检查
                corrected_words.append(word)
                continue
            
            corrected = self.correction(word, max_edits)
            if corrected != word.lower():
                corrections.append((word, corrected))
                # 保持原大小写
                if word[0].isupper():
                    corrected = corrected.capitalize()
                corrected_words.append(corrected)
            else:
                corrected_words.append(word)
        
        # 重建查询字符串（简单替换）
        corrected_query = query
        for original, corrected in corrections:
            corrected_query = corrected_query.replace(original, corrected, 1)
        
        return corrected_query, corrections
    
    def suggest(self, word, n=5, max_edits=2):
        """
        返回拼写建议列表
        
        Args:
            word: 待检查的词
            n: 建议数量
            max_edits: 最大编辑距离
        
        Returns:
            list: [(suggestion, probability)]
        """
        candidates = self.candidates(word, max_edits)
        if not candidates:
            return []
        
        # 按概率排序
        scored = [(c, self.probability(c)) for c in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)
        
        return scored[:n]
