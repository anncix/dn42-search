# -*- coding: utf-8 -*-
"""
PageRank 算法实现

PageRank 由 Larry Page 和 Sergey Brin 提出，
基于"随机冲浪者模型"计算页面的重要性。

公式：
PR(p_i) = (1 - d) / N + d * Σ(PR(p_j) / L(p_j))

其中：
- d: 阻尼因子（通常 0.85）
- N: 页面总数
- M(p_i): 所有链接到 p_i 的页面集合
- L(p_j): 页面 p_j 的出链数量

使用幂迭代法求解，直到收敛。
"""
import time
from collections import defaultdict
from config import PAGERANK_CONFIG
from utils.logger import get_logger

logger = get_logger('ranker.pagerank')


class PageRankCalculator:
    """PageRank 计算器"""
    
    def __init__(self, damping_factor=None, max_iterations=None, tolerance=None):
        self.damping_factor = damping_factor or PAGERANK_CONFIG['damping_factor']
        self.max_iterations = max_iterations or PAGERANK_CONFIG['max_iterations']
        self.tolerance = tolerance or PAGERANK_CONFIG['tolerance']
    
    def compute(self, links, all_pages=None):
        """
        计算 PageRank
        
        Args:
            links: 链接列表，[(from_doc_id, to_doc_id)]
            all_pages: 所有页面的 doc_id 列表（如果有孤立页面）
        
        Returns:
            dict: {doc_id: pagerank_value}
        """
        start_time = time.time()
        
        # 构建邻接表
        out_links = defaultdict(list)  # from -> [to]
        in_links = defaultdict(list)   # to -> [from]
        
        for from_id, to_id in links:
            if from_id and to_id:
                out_links[from_id].append(to_id)
                in_links[to_id].append(from_id)
        
        # 收集所有页面
        pages = set()
        if all_pages:
            pages.update(all_pages)
        for from_id, to_id in links:
            if from_id:
                pages.add(from_id)
            if to_id:
                pages.add(to_id)
        
        N = len(pages)
        if N == 0:
            logger.warning("没有页面数据，无法计算 PageRank")
            return {}
        
        logger.info(f"开始计算 PageRank: {N} 个页面, {len(links)} 条链接")
        
        # 初始化 PageRank 值（均匀分布）
        pagerank = {page: 1.0 / N for page in pages}
        
        # 找出悬空节点（没有出链的页面）
        dangling_nodes = [page for page in pages if len(out_links[page]) == 0]
        
        d = self.damping_factor
        
        # 幂迭代
        for iteration in range(self.max_iterations):
            new_pagerank = {}
            
            # 计算悬空节点的 PageRank 总和（均匀分配给所有页面）
            dangling_sum = sum(pagerank[node] for node in dangling_nodes)
            dangling_contrib = d * dangling_sum / N
            
            # 基础值（随机跳转）
            base = (1 - d) / N + dangling_contrib
            
            max_diff = 0.0
            
            for page in pages:
                # 入链贡献
                rank_sum = 0.0
                for in_page in in_links[page]:
                    out_count = len(out_links[in_page])
                    if out_count > 0:
                        rank_sum += pagerank[in_page] / out_count
                
                new_rank = base + d * rank_sum
                new_pagerank[page] = new_rank
                
                diff = abs(new_rank - pagerank[page])
                max_diff = max(max_diff, diff)
            
            pagerank = new_pagerank
            
            logger.debug(
                f"PageRank 迭代 {iteration + 1}: "
                f"max_diff = {max_diff:.8f}"
            )
            
            # 检查收敛
            if max_diff < self.tolerance:
                logger.info(
                    f"PageRank 收敛！迭代次数: {iteration + 1}, "
                    f"max_diff: {max_diff:.8f}"
                )
                break
        
        elapsed = time.time() - start_time
        logger.info(
            f"PageRank 计算完成，耗时 {elapsed:.2f} 秒"
        )
        
        # 归一化（确保总和为 1）
        total = sum(pagerank.values())
        if total > 0:
            pagerank = {k: v / total for k, v in pagerank.items()}
        
        return pagerank
    
    def compute_from_db(self, db):
        """
        从数据库计算 PageRank 并保存结果
        
        Args:
            db: Database 实例
        
        Returns:
            dict: {doc_id: pagerank_value}
        """
        # 获取所有链接
        links = db.get_all_links()
        
        # 获取所有页面的 doc_id
        pages = db.get_all_pages()
        all_doc_ids = [page['doc_id'] for page in pages]
        
        # 计算 PageRank
        pagerank = self.compute(links, all_doc_ids)
        
        # 保存到数据库
        for doc_id, rank in pagerank.items():
            db.update_page_pagerank(doc_id, rank)
        
        logger.info(f"已将 {len(pagerank)} 个页面的 PageRank 保存到数据库")
        
        return pagerank
    
    def get_top_pages(self, pagerank, n=10):
        """获取 PageRank 最高的页面"""
        sorted_pages = sorted(pagerank.items(), key=lambda x: x[1], reverse=True)
        return sorted_pages[:n]
    
    def print_stats(self, pagerank):
        """打印 PageRank 统计信息"""
        if not pagerank:
            return
        
        values = list(pagerank.values())
        values.sort(reverse=True)
        
        logger.info(f"PageRank 统计:")
        logger.info(f"  页面数: {len(values)}")
        logger.info(f"  最大值: {values[0]:.8f}")
        logger.info(f"  最小值: {values[-1]:.8f}")
        logger.info(f"  平均值: {sum(values)/len(values):.8f}")
        
        # Top 10
        logger.info(f"  Top 10:")
        for i, (doc_id, rank) in enumerate(sorted(pagerank.items(), key=lambda x: x[1], reverse=True)[:10]):
            logger.info(f"    {i+1}. {doc_id}: {rank:.8f}")
