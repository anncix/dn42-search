# -*- coding: utf-8 -*-
"""
倒排索引实现
支持内存索引和磁盘持久化，使用可变字节编码压缩
"""
import os
import struct
import json
import time
import array
from collections import defaultdict
from config import INDEX_CONFIG
from utils.logger import get_logger

logger = get_logger('indexer.index')


class InvertedIndex:
    """
    倒排索引
    
    数据结构：
    - 词典 (Dictionary): term -> (df, postings_offset, postings_size)
    - 倒排列表 (Postings): 文档ID列表 + 词频 + 位置信息
    - 文档元数据: doc_id -> (url, title, length, pagerank)
    """
    
    # 每个词项在每个文档中最多保存的位置信息数量
    MAX_POSITIONS = 100
    
    def __init__(self, index_path=None):
        self.config = INDEX_CONFIG
        self.index_path = index_path or self.config['index_path']
        os.makedirs(self.index_path, exist_ok=True)
        
        # 内存中的倒排索引
        # term -> {doc_id: {'freq': int, 'positions': [int], 'fields': set}}
        self._postings = defaultdict(dict)
        
        # 文档元数据
        # doc_id -> {'url': str, 'title': str, 'length': int, 'pagerank': float}
        self._doc_info = {}
        
        # 词典（词项 -> 文档频率）
        # term -> df
        self._dictionary = {}
        
        # 平均文档长度（用于 BM25）
        self._avg_doc_length = 0.0
        
        # 文档总数
        self._total_docs = 0
        
        # 字段权重
        self.field_weights = self.config['field_weights']
    
    def add_document(self, doc_id, fields):
        """
        添加文档到索引
        
        Args:
            doc_id: 文档 ID
            fields: 字段字典，如 {'title': '...', 'body': '...', 'url': '...'}
        """
        from indexer.tokenizer import Tokenizer
        
        tokenizer = Tokenizer()
        
        # 合并所有字段的词项（考虑权重）
        doc_terms = {}  # term -> {freq, positions, fields}
        doc_length = 0
        
        for field_name, field_content in fields.items():
            if not field_content:
                continue
            
            tokens = tokenizer.tokenize(field_content, field=field_name)
            weight = self.field_weights.get(field_name, 1.0)
            doc_length += len(tokens)
            
            for pos, token in enumerate(tokens):
                if token not in doc_terms:
                    doc_terms[token] = {
                        'freq': 0,
                        'positions': [],
                        'fields': set(),
                    }
                doc_terms[token]['freq'] += weight
                doc_terms[token]['positions'].append(pos)
                doc_terms[token]['fields'].add(field_name)
        
        # 添加到倒排索引
        for term, info in doc_terms.items():
            self._postings[term][doc_id] = {
                'freq': info['freq'],
                'positions': info['positions'][:self.MAX_POSITIONS],
                'fields': info['fields'],
            }
        
        # 更新文档元数据
        self._doc_info[doc_id] = {
            'url': fields.get('url', ''),
            'title': fields.get('title', ''),
            'length': doc_length,
            'pagerank': 0.0,
        }
        
        self._total_docs += 1
        
        # 更新平均文档长度
        if self._total_docs == 1:
            self._avg_doc_length = doc_length
        else:
            self._avg_doc_length += (doc_length - self._avg_doc_length) / self._total_docs
    
    def update_pagerank(self, doc_id, pagerank):
        """更新文档的 PageRank 值"""
        if doc_id in self._doc_info:
            self._doc_info[doc_id]['pagerank'] = pagerank
    
    def get_postings(self, term):
        """获取词项的倒排列表"""
        return self._postings.get(term, {})
    
    def get_doc_info(self, doc_id):
        """获取文档信息"""
        return self._doc_info.get(doc_id)
    
    def doc_frequency(self, term):
        """获取词项的文档频率"""
        return len(self._postings.get(term, {}))
    
    @property
    def total_docs(self):
        return self._total_docs
    
    @property
    def avg_doc_length(self):
        return self._avg_doc_length
    
    @property
    def vocabulary_size(self):
        return len(self._postings)
    
    def get_all_terms(self):
        """获取所有词项"""
        return list(self._postings.keys())
    
    # ========== 持久化 ==========
    
    def save(self, path=None):
        """
        保存索引到磁盘
        
        索引文件格式：
        - index_meta.json: 元数据（文档数、平均长度等）
        - dictionary.json: 词典（词项 -> 文档频率）
        - postings.bin: 倒排列表（二进制）
        - doc_info.json: 文档元数据
        """
        save_path = path or self.index_path
        os.makedirs(save_path, exist_ok=True)
        
        # 保存元数据
        meta = {
            'total_docs': self._total_docs,
            'avg_doc_length': self._avg_doc_length,
            'vocabulary_size': len(self._postings),
            'created_at': time.time(),
            'version': 1,
        }
        with open(os.path.join(save_path, 'index_meta.json'), 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        
        # 保存文档信息
        doc_info_serializable = {}
        for doc_id, info in self._doc_info.items():
            doc_info_serializable[doc_id] = {
                'url': info['url'],
                'title': info['title'],
                'length': info['length'],
                'pagerank': info['pagerank'],
            }
        with open(os.path.join(save_path, 'doc_info.json'), 'w', encoding='utf-8') as f:
            json.dump(doc_info_serializable, f, ensure_ascii=False)
        
        # 保存词典和倒排列表
        dictionary = {}
        postings_data = bytearray()
        offset = 0
        
        for term in sorted(self._postings.keys()):
            postings = self._postings[term]
            df = len(postings)
            
            # 编码倒排列表
            encoded = self._encode_postings(postings)
            size = len(encoded)
            
            dictionary[term] = {
                'df': df,
                'offset': offset,
                'size': size,
            }
            
            postings_data.extend(encoded)
            offset += size
        
        # 保存词典
        with open(os.path.join(save_path, 'dictionary.json'), 'w', encoding='utf-8') as f:
            json.dump(dictionary, f, ensure_ascii=False)
        
        # 保存倒排列表
        with open(os.path.join(save_path, 'postings.bin'), 'wb') as f:
            f.write(postings_data)
        
        logger.info(
            f"索引已保存到 {save_path}: "
            f"{self._total_docs} 文档, "
            f"{len(self._postings)} 词项, "
            f"{len(postings_data)} 字节倒排列表"
        )
    
    def load(self, path=None):
        """
        从磁盘加载索引
        """
        load_path = path or self.index_path
        
        meta_path = os.path.join(load_path, 'index_meta.json')
        if not os.path.exists(meta_path):
            logger.warning(f"索引不存在: {load_path}")
            return False
        
        # 加载元数据
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta = json.load(f)
        
        self._total_docs = meta.get('total_docs', 0)
        self._avg_doc_length = meta.get('avg_doc_length', 0)
        
        # 加载文档信息
        doc_info_path = os.path.join(load_path, 'doc_info.json')
        if os.path.exists(doc_info_path):
            with open(doc_info_path, 'r', encoding='utf-8') as f:
                self._doc_info = json.load(f)
        
        # 加载词典和倒排列表
        dict_path = os.path.join(load_path, 'dictionary.json')
        postings_path = os.path.join(load_path, 'postings.bin')
        
        if os.path.exists(dict_path) and os.path.exists(postings_path):
            with open(dict_path, 'r', encoding='utf-8') as f:
                dictionary = json.load(f)
            
            with open(postings_path, 'rb') as f:
                postings_data = f.read()
            
            # 解码所有倒排列表（加载到内存）
            self._postings = defaultdict(dict)
            for term, info in dictionary.items():
                offset = info['offset']
                size = info['size']
                data = postings_data[offset:offset+size]
                self._postings[term] = self._decode_postings(data)
            
            self._dictionary = {term: info['df'] for term, info in dictionary.items()}
        
        logger.info(
            f"索引已从 {load_path} 加载: "
            f"{self._total_docs} 文档, "
            f"{len(self._postings)} 词项"
        )
        
        return True
    
    def _encode_postings(self, postings):
        """
        编码倒排列表为二进制格式（可变字节编码）
        
        格式：
        [doc_count: varint]
        [doc_id_len: varint][doc_id: bytes][freq: varint][field_count: varint][fields...][pos_count: varint][positions: varint...]
        ...
        """
        data = bytearray()
        
        # 文档数量
        self._encode_varint(data, len(postings))
        
        # 按 doc_id 排序（便于差值编码）
        for doc_id, info in sorted(postings.items(), key=lambda x: x[0]):
            # doc_id（字符串长度 + 内容）
            doc_id_bytes = doc_id.encode('utf-8')
            self._encode_varint(data, len(doc_id_bytes))
            data.extend(doc_id_bytes)
            
            # 词频
            freq = int(info['freq'] * 10)  # 乘以 10 保留一位小数
            self._encode_varint(data, freq)
            
            # 字段信息
            fields = sorted(info.get('fields', set()))
            self._encode_varint(data, len(fields))
            for field_name in fields:
                field_bytes = field_name.encode('utf-8')
                self._encode_varint(data, len(field_bytes))
                data.extend(field_bytes)
            
            # 位置信息 - 截断到 MAX_POSITIONS，pos_count 必须与实际编码数量一致
            positions = info.get('positions', [])[:self.MAX_POSITIONS]
            self._encode_varint(data, len(positions))
            
            # 位置差值编码
            prev_pos = 0
            for pos in positions:
                self._encode_varint(data, pos - prev_pos)
                prev_pos = pos
        
        return bytes(data)
    
    def _decode_postings(self, data):
        """解码倒排列表"""
        postings = {}
        pos = 0
        
        # 文档数量
        doc_count, pos = self._decode_varint(data, pos)
        
        for _ in range(doc_count):
            # doc_id 长度
            id_len, pos = self._decode_varint(data, pos)
            doc_id = data[pos:pos+id_len].decode('utf-8')
            pos += id_len
            
            # 词频
            freq, pos = self._decode_varint(data, pos)
            freq = freq / 10.0  # 还原小数
            
            # 字段信息
            field_count, pos = self._decode_varint(data, pos)
            fields = set()
            for _ in range(field_count):
                field_len, pos = self._decode_varint(data, pos)
                field_name = data[pos:pos+field_len].decode('utf-8')
                pos += field_len
                fields.add(field_name)
            
            # 位置数量
            pos_count, pos = self._decode_varint(data, pos)
            
            # 位置信息
            positions = []
            prev_pos = 0
            for _ in range(pos_count):
                delta, pos = self._decode_varint(data, pos)
                prev_pos += delta
                positions.append(prev_pos)
            
            postings[doc_id] = {
                'freq': freq,
                'positions': positions,
                'fields': fields,
            }
        
        return postings
    
    def _encode_varint(self, data, value):
        """可变字节编码（每个字节7位数据，最高位为续位标记）"""
        value = int(value)
        while value > 127:
            data.append((value & 0x7F) | 0x80)
            value >>= 7
        data.append(value & 0x7F)
    
    def _decode_varint(self, data, pos):
        """解码可变字节编码的整数"""
        result = 0
        shift = 0
        while pos < len(data):
            byte = data[pos]
            pos += 1
            result |= (byte & 0x7F) << shift
            if not (byte & 0x80):
                break
            shift += 7
        return result, pos
    
    def clear(self):
        """清空索引"""
        self._postings.clear()
        self._doc_info.clear()
        self._dictionary.clear()
        self._total_docs = 0
        self._avg_doc_length = 0.0
    
    def stats(self):
        """获取索引统计信息"""
        total_postings = sum(len(p) for p in self._postings.values())
        return {
            'total_docs': self._total_docs,
            'vocabulary_size': len(self._postings),
            'total_postings': total_postings,
            'avg_doc_length': self._avg_doc_length,
            'avg_terms_per_doc': total_postings / self._total_docs if self._total_docs else 0,
        }
