# -*- coding: utf-8 -*-
"""
分词器（Tokenizer）
支持中英文分词、停用词过滤、词干提取
"""
import re
import math
from utils.logger import get_logger

logger = get_logger('indexer.tokenizer')


class Tokenizer:
    """文本分词器"""
    
    def __init__(self):
        # 停用词集合
        self.stop_words = self._load_stop_words()
        
        # 词干提取规则（简单的 Porter stemmer 简化版）
        self._stem_rules = self._init_stem_rules()
    
    def _load_stop_words(self):
        """加载停用词"""
        # 英文停用词
        english = {
            'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
            'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'could', 'should', 'may', 'might', 'can', 'shall', 'this', 'that',
            'these', 'those', 'it', 'its', 'he', 'his', 'she', 'her', 'they',
            'them', 'their', 'we', 'our', 'you', 'your', 'i', 'me', 'my', 'mine',
            'what', 'which', 'who', 'whom', 'when', 'where', 'why', 'how', 'all',
            'each', 'every', 'both', 'few', 'more', 'most', 'other', 'some', 'such',
            'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very',
            'just', 'about', 'up', 'out', 'down', 'over', 'under', 'again',
            'further', 'then', 'once', 'here', 'there', 'also', 'if', 'because',
            'as', 'until', 'while', 'after', 'before', 'above', 'below',
            'between', 'through', 'during', 'into', 'throughout', 'despite',
            'unless', 'until', 'whenever', 'wherever', 'however', 'moreover',
            'therefore', 'thus', 'hence', 'since', 'because',
            'www', 'com', 'org', 'net', 'edu', 'gov', 'io', 'html', 'htm',
            'http', 'https', 'ftp',
        }
        
        # 中文停用词
        chinese = {
            '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一',
            '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没',
            '看', '好', '自己', '这', '那', '他', '她', '它', '们', '而', '与', '及',
            '或', '但', '然', '则', '虽', '既', '又', '且', '并', '且', '并', '及',
            '等', '等等', '之类', '什么', '怎么', '为什么', '如何', '可以', '能',
            '能够', '应该', '必须', '需要', '知道', '明白', '理解', '觉得', '认为',
            '因为', '所以', '因此', '于是', '如果', '假如', '假设', '即使', '虽然',
            '但是', '不过', '然而', '其实', '实际上', '事实上', '当然', '显然',
            '这个', '那个', '这些', '那些', '这样', '那样', '这里', '那里',
            '现在', '过去', '将来', '已经', '正在', '将要', '曾经', '一直',
            '总是', '经常', '常常', '偶尔', '有时', '从不', '绝不',
            '中', '内', '外', '上', '下', '左', '右', '前', '后', '里', '外',
            '之间', '之中', '之内', '之外', '以上', '以下', '以前', '以后',
            '是', '为', '以', '及', '等', '也', '都', '还', '又', '再', '已',
        }
        
        return english | chinese
    
    def _init_stem_rules(self):
        """初始化词干提取规则（简化版 Porter stemmer）"""
        # 后缀替换规则：(后缀, 替换为, 最小词干长度)
        rules = [
            # 复数和第三人称
            ('sses', 'ss', 3),
            ('ies', 'i', 3),
            ('ss', 'ss', 2),
            ('s', '', 3),
            
            # 过去式和进行时
            ('eed', 'ee', 3),
            ('ed', '', 3),
            ('ing', '', 3),
            
            # 形容词
            ('ational', 'ate', 5),
            ('tional', 'tion', 5),
            ('enci', 'ence', 4),
            ('anci', 'ance', 4),
            ('izer', 'ize', 4),
            ('abli', 'able', 4),
            ('alli', 'al', 4),
            ('entli', 'ent', 5),
            ('eli', 'e', 3),
            ('ousli', 'ous', 4),
            ('ization', 'ize', 6),
            ('ation', 'ate', 5),
            ('ator', 'ate', 4),
            ('alism', 'al', 5),
            ('iveness', 'ive', 6),
            ('fulness', 'ful', 6),
            ('ousness', 'ous', 6),
            
            # 副词等
            ('al', '', 3),
            ('ance', '', 4),
            ('ence', '', 4),
            ('er', '', 3),
            ('ic', '', 3),
            ('able', '', 4),
            ('ible', '', 4),
            ('ment', '', 4),
            ('ness', '', 4),
            ('ful', '', 3),
            ('ous', '', 3),
            ('ive', '', 3),
            ('ize', '', 3),
        ]
        return rules
    
    def tokenize(self, text, field='body', enable_stemming=True):
        """
        分词主函数
        
        Args:
            text: 输入文本
            field: 字段类型（影响权重计算）
            enable_stemming: 是否启用词干提取
        
        Returns:
            list: 词项列表
        """
        if not text:
            return []
        
        tokens = []
        
        # 提取英文单词（含数字）
        english_tokens = re.findall(r'[a-zA-Z][a-zA-Z0-9]*', text.lower())
        tokens.extend(english_tokens)
        
        # 提取中文（简单按字符切分，实际应使用分词库如 jieba）
        # 这里用 2-gram 和 3-gram 方式处理中文，提供基本的中文搜索能力
        chinese_chars = re.findall(r'[\u4e00-\u9fff]+', text)
        for chars in chinese_chars:
            # 单字
            tokens.extend(list(chars))
            # 2-gram
            if len(chars) >= 2:
                for i in range(len(chars) - 1):
                    tokens.append(chars[i:i+2])
            # 3-gram
            if len(chars) >= 3:
                for i in range(len(chars) - 2):
                    tokens.append(chars[i:i+3])
        
        # 过滤停用词和短词
        tokens = [t for t in tokens if len(t) >= 2 and t not in self.stop_words]
        
        # 词干提取（仅英文）
        if enable_stemming:
            stemmed = []
            for token in tokens:
                if re.match(r'^[a-zA-Z]+$', token):
                    stemmed.append(self._stem(token))
                else:
                    stemmed.append(token)
            tokens = stemmed
        
        return tokens
    
    def _stem(self, word):
        """简单词干提取"""
        if len(word) <= 3:
            return word
        
        for suffix, replacement, min_len in self._stem_rules:
            if word.endswith(suffix) and len(word) > min_len:
                return word[:-len(suffix)] + replacement
        
        return word
    
    def count_terms(self, tokens, field_weights=None):
        """
        统计词频（考虑字段权重）
        
        Args:
            tokens: 词项列表
            field_weights: 字段权重字典，如 {'title': 5.0, 'body': 1.0}
        
        Returns:
            dict: {term: weighted_frequency}
        """
        freq = {}
        weight = field_weights.get('body', 1.0) if field_weights else 1.0
        
        for token in tokens:
            freq[token] = freq.get(token, 0) + weight
        
        return freq
    
    def tokenize_with_positions(self, text):
        """
        分词并记录位置信息（用于短语查询和邻近查询）
        
        Returns:
            dict: {term: [positions]}
        """
        if not text:
            return {}
        
        positions = {}
        pos = 0
        
        # 简单的按空格和标点分割
        words = re.findall(r'\b\w+\b', text.lower())
        
        for i, word in enumerate(words):
            if word in self.stop_words or len(word) < 2:
                continue
            
            stemmed = self._stem(word) if re.match(r'^[a-zA-Z]+$', word) else word
            
            if stemmed not in positions:
                positions[stemmed] = []
            positions[stemmed].append(i)
        
        return positions
