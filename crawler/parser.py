# -*- coding: utf-8 -*-
"""
HTML 页面解析器
提取文本内容、链接、标题等信息
"""
import re
import hashlib
from bs4 import BeautifulSoup
from utils.logger import get_logger

logger = get_logger('crawler.parser')


class PageParser:
    """页面解析器"""
    
    def __init__(self):
        self._stop_words = set()
        self._init_stop_words()
    
    def _init_stop_words(self):
        """初始化停用词（中英文）"""
        # 英文停用词
        english_stop = {
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
            'as', 'until', 'while', 'of', 'after', 'before', 'above', 'below',
            'between', 'through', 'during', 'before', 'after'
        }
        self._stop_words = english_stop
    
    def parse(self, html_content, base_url):
        """
        解析 HTML 页面
        
        Returns:
            dict: 包含标题、文本、链接等信息
        """
        result = {
            'title': '',
            'text': '',
            'links': [],
            'headings': [],
            'meta_description': '',
            'meta_keywords': '',
            'content_hash': '',
            'text_length': 0,
        }
        
        if not html_content:
            return result
        
        try:
            soup = BeautifulSoup(html_content, 'lxml')
            
            # 提取标题
            if soup.title and soup.title.string:
                result['title'] = soup.title.string.strip()
            
            # 提取 meta 标签
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc and meta_desc.get('content'):
                result['meta_description'] = meta_desc['content'].strip()
            
            meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
            if meta_keywords and meta_keywords.get('content'):
                result['meta_keywords'] = meta_keywords['content'].strip()
            
            # 提取标题标签
            for tag in ['h1', 'h2', 'h3']:
                for heading in soup.find_all(tag):
                    text = heading.get_text(strip=True)
                    if text:
                        result['headings'].append((tag, text))
            
            # 移除不需要的标签
            for tag in soup(['script', 'style', 'noscript', 'iframe', 'svg', 'canvas']):
                tag.decompose()
            
            # 提取所有文本
            text = soup.get_text(separator='\n', strip=True)
            # 清理多余空白
            text = re.sub(r'\s+', ' ', text).strip()
            result['text'] = text
            result['text_length'] = len(text)
            
            # 计算内容哈希
            result['content_hash'] = hashlib.sha256(text.encode('utf-8')).hexdigest()
            
            # 提取链接
            result['links'] = self._extract_links(soup, base_url)
            
        except Exception as e:
            logger.error(f"解析页面失败: {base_url}, {e}")
        
        return result
    
    def _extract_links(self, soup, base_url):
        """提取页面中的所有链接"""
        from utils.url_utils import resolve_url, is_valid_url, normalize_url
        
        links = []
        seen = set()
        
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href'].strip()
            
            # 跳过空链接和锚点
            if not href or href.startswith('#'):
                continue
            
            # 跳过非 HTTP 链接
            if href.startswith(('javascript:', 'mailto:', 'tel:', 'ftp:', 'data:')):
                continue
            
            # 解析为绝对 URL
            abs_url = resolve_url(base_url, href)
            if not abs_url or not is_valid_url(abs_url):
                continue
            
            # 规范化 URL
            abs_url = normalize_url(abs_url)
            
            if abs_url in seen:
                continue
            seen.add(abs_url)
            
            # 获取锚文本
            anchor_text = a_tag.get_text(strip=True)
            # 也考虑 title 属性
            if not anchor_text and a_tag.get('title'):
                anchor_text = a_tag['title'].strip()
            
            links.append({
                'url': abs_url,
                'anchor': anchor_text[:200] if anchor_text else '',  # 限制长度
            })
        
        return links
    
    def extract_keywords(self, text, top_n=20):
        """从文本中提取关键词（简单词频统计）"""
        if not text:
            return []
        
        # 简单分词（按空白和标点）
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        
        # 过滤停用词
        words = [w for w in words if w not in self._stop_words]
        
        # 统计词频
        freq = {}
        for word in words:
            freq[word] = freq.get(word, 0) + 1
        
        # 排序返回 top N
        sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, count in sorted_words[:top_n]]
