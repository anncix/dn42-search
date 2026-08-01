#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DN42 搜索引擎主入口
支持命令行操作：爬取、建索引、计算 PageRank、启动 Web 服务
"""
import sys
import os
import asyncio
import argparse

# 将项目根目录加入路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.logger import setup_logger
from storage.db import Database
from crawler.crawler import Crawler
from indexer.builder import IndexBuilder
from indexer.index import InvertedIndex
from ranker.pagerank import PageRankCalculator
from searcher.searcher import SearchEngine
from web import create_app

logger = setup_logger()


def cmd_crawl(args):
    """执行爬取任务"""
    logger.info("=" * 60)
    logger.info("启动 DN42 爬虫")
    logger.info("=" * 60)
    
    db = Database()
    crawler = Crawler(db)
    
    try:
        asyncio.run(crawler.crawl(
            max_pages=args.max_pages,
            max_duration=args.max_duration
        ))
    except KeyboardInterrupt:
        logger.info("用户中断")
    finally:
        crawler.close()
    
    logger.info("爬取完成")


def cmd_index(args):
    """构建索引"""
    logger.info("=" * 60)
    logger.info("构建倒排索引")
    logger.info("=" * 60)
    
    db = Database()
    index = InvertedIndex()
    builder = IndexBuilder(db, index)
    
    count = builder.build_from_database()
    logger.info(f"索引构建完成，共 {count} 个文档")
    
    db.close()


def cmd_pagerank(args):
    """计算 PageRank"""
    logger.info("=" * 60)
    logger.info("计算 PageRank")
    logger.info("=" * 60)
    
    db = Database()
    calculator = PageRankCalculator()
    pagerank = calculator.compute_from_db(db)
    
    # 打印 Top 10
    top = calculator.get_top_pages(pagerank, n=10)
    logger.info("\nPageRank Top 10:")
    for i, (doc_id, rank) in enumerate(top):
        page = db.get_page(doc_id=doc_id)
        title = page['title'] if page else doc_id
        url = page['url'] if page else ''
        logger.info(f"  {i+1}. [{rank:.8f}] {title}")
        if url:
            logger.info(f"     {url}")
    
    # 重新保存索引（更新 PageRank）
    index = InvertedIndex()
    index.load()
    for doc_id, rank in pagerank.items():
        index.update_pagerank(doc_id, rank)
    index.save()
    logger.info("索引已更新 PageRank")
    
    db.close()


def cmd_web(args):
    """启动 Web 服务"""
    from config import WEB_CONFIG
    
    logger.info("=" * 60)
    logger.info("启动 DN42 Search Web 服务")
    logger.info("=" * 60)
    
    # 初始化搜索引擎
    db = Database()
    engine = SearchEngine(db)
    
    # 加载索引
    if not engine.load_index():
        logger.warning("索引未找到，使用空索引启动服务")
    
    # 创建 Flask 应用
    app = create_app(engine)
    
    logger.info(f"服务启动在 http://{WEB_CONFIG['host']}:{WEB_CONFIG['port']}")
    
    app.run(
        host=WEB_CONFIG['host'],
        port=WEB_CONFIG['port'],
        debug=WEB_CONFIG['debug']
    )
    
    db.close()


def cmd_stats(args):
    """显示统计信息"""
    db = Database()
    engine = SearchEngine(db)
    engine.load_index()
    
    stats = engine.get_stats()
    
    print("\n" + "=" * 60)
    print("DN42 Search 统计信息")
    print("=" * 60)
    
    print(f"\n索引状态: {'已加载' if stats['index_loaded'] else '未加载'}")
    print(f"已抓取页面: {stats['pages_crawled']}")
    
    if stats['index_loaded'] and stats.get('index'):
        idx = stats['index']
        print(f"\n--- 索引详情 ---")
        print(f"文档数: {idx.get('total_docs', 0)}")
        print(f"词项数: {idx.get('vocabulary_size', 0)}")
        print(f"倒排列表项: {idx.get('total_postings', 0)}")
        print(f"平均文档长度: {idx.get('avg_doc_length', 0):.1f}")
    
    print(f"\n--- 链接统计 ---")
    links = stats.get('links', {})
    print(f"总链接数: {links.get('total', 0)}")
    print(f"源页面数: {links.get('unique_from', 0)}")
    print(f"目标页面数: {links.get('unique_to', 0)}")
    
    print(f"\n--- 队列状态 ---")
    queue = db.get_queue_stats()
    for status, count in queue.items():
        print(f"  {status}: {count}")
    
    print("\n" + "=" * 60 + "\n")
    
    db.close()


def cmd_init(args):
    """初始化项目（创建数据库等）"""
    logger.info("初始化 DN42 Search...")
    
    db = Database()
    
    # 添加种子 URL
    from config import DN42_CONFIG
    for url in DN42_CONFIG['seed_urls']:
        db.add_url(url, depth=0, priority=1)
    
    logger.info(f"已添加 {len(DN42_CONFIG['seed_urls'])} 个种子 URL")
    logger.info("初始化完成！可以使用 crawl 命令开始爬取")
    
    db.close()


def main():
    parser = argparse.ArgumentParser(
        description='DN42 Search - 去中心化网络搜索引擎',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s init              # 初始化项目
  %(prog)s crawl             # 开始爬取
  %(prog)s crawl -n 1000     # 爬取最多 1000 个页面
  %(prog)s index             # 构建倒排索引
  %(prog)s pagerank          # 计算 PageRank
  %(prog)s web               # 启动 Web 搜索服务
  %(prog)s stats             # 显示统计信息
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # init 命令
    init_parser = subparsers.add_parser('init', help='初始化项目')
    init_parser.set_defaults(func=cmd_init)
    
    # crawl 命令
    crawl_parser = subparsers.add_parser('crawl', help='执行爬取任务')
    crawl_parser.add_argument('-n', '--max-pages', type=int, default=None,
                             help='最大爬取页面数')
    crawl_parser.add_argument('-t', '--max-duration', type=int, default=None,
                             help='最大运行时间（秒）')
    crawl_parser.set_defaults(func=cmd_crawl)
    
    # index 命令
    index_parser = subparsers.add_parser('index', help='构建倒排索引')
    index_parser.set_defaults(func=cmd_index)
    
    # pagerank 命令
    pr_parser = subparsers.add_parser('pagerank', help='计算 PageRank')
    pr_parser.set_defaults(func=cmd_pagerank)
    
    # web 命令
    web_parser = subparsers.add_parser('web', help='启动 Web 搜索服务')
    web_parser.set_defaults(func=cmd_web)
    
    # stats 命令
    stats_parser = subparsers.add_parser('stats', help='显示统计信息')
    stats_parser.set_defaults(func=cmd_stats)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == '__main__':
    main()
