# DN42 Search - 去中心化网络搜索引擎

一个专为 [dn42](https://wiki.dn42/) 去中心化网络设计的开源搜索引擎，
借鉴 Google 等主流搜索引擎的核心技术架构，包括网络爬虫、倒排索引、BM25 排序算法和 PageRank 链接分析。

## 特性

- **异步爬虫**：基于 asyncio + aiohttp 的高并发爬虫，支持礼貌爬取
- **倒排索引**：自研倒排索引引擎，可变字节编码压缩
- **BM25 排序**：经典概率检索模型，考虑词频饱和和文档长度归一化
- **PageRank**：基于链接图的权威度计算，幂迭代法求解
- **拼写检查**：基于编辑距离 + 语言模型的自动纠错
- **Web 界面**：Google 风格的搜索界面，支持多种排序模式
- **dn42 原生**：严格限制爬取范围为 dn42 网络

## 技术架构

```
┌─────────────────────────────────────────────────────────┐
│                      Web 前端 (Flask)                    │
│              搜索界面 / 结果页 / API / 统计               │
└──────────────────────────────┬──────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────┐
│                    搜索服务层 (Searcher)                 │
│        查询解析 / 拼写检查 / 排序整合 / 结果生成          │
└──────────────────────────────┬──────────────────────────┘
                               │
          ┌────────────────────┴────────────────────┐
          │                                         │
┌─────────▼──────────┐                    ┌─────────▼──────────┐
│   索引引擎 (Index)  │                    │  排序器 (Ranker)   │
│  倒排索引 / 分词器  │                    │  BM25 / PageRank   │
│  磁盘持久化 / 压缩  │                    │  混合排序策略      │
└─────────▲──────────┘                    └─────────▲──────────┘
          │                                         │
          └────────────────────┬────────────────────┘
                               │
┌──────────────────────────────┴──────────────────────────┐
│                    存储层 (SQLite)                       │
│           页面元数据 / URL 队列 / 链接关系               │
└──────────────────────────────▲──────────────────────────┘
                               │
┌──────────────────────────────┴──────────────────────────┐
│                    爬虫层 (Crawler)                      │
│   URL Frontier / 异步下载 / HTML 解析 / robots.txt      │
└─────────────────────────────────────────────────────────┘
```

## 目录结构

```
dn42-search/
├── run.py                  # 主入口文件
├── config.py               # 配置文件
├── requirements.txt        # Python 依赖
├── crawler/                # 爬虫模块
│   ├── crawler.py          # 主爬虫引擎（异步）
│   ├── frontier.py         # URL 调度队列
│   ├── parser.py           # HTML 解析器
│   └── __init__.py
├── indexer/                # 索引模块
│   ├── index.py            # 倒排索引实现
│   ├── tokenizer.py        # 分词器
│   ├── builder.py          # 索引构建器
│   └── __init__.py
├── ranker/                 # 排序模块
│   ├── bm25.py             # BM25 算法
│   ├── pagerank.py         # PageRank 算法
│   ├── ranker.py           # 综合排序器
│   └── __init__.py
├── searcher/               # 搜索服务
│   ├── searcher.py         # 搜索引擎主类
│   ├── query.py            # 查询处理器
│   ├── spellcheck.py       # 拼写检查器
│   └── __init__.py
├── storage/                # 数据存储
│   ├── db.py               # SQLite 数据库
│   └── __init__.py
├── web/                    # Web 前端
│   ├── routes.py           # 路由
│   ├── templates/          # HTML 模板
│   ├── static/             # 静态资源（CSS/JS）
│   └── __init__.py
├── utils/                  # 工具函数
│   ├── logger.py           # 日志工具
│   ├── url_utils.py        # URL 工具
│   └── __init__.py
├── data/                   # 数据目录（运行时生成）
└── logs/                   # 日志目录（运行时生成）
```

## 快速开始

### 1. 安装依赖

```bash
cd dn42-search
pip install -r requirements.txt
```

### 2. 初始化项目

```bash
python run.py init
```

这会创建数据库并添加种子 URL。

### 3. 开始爬取

```bash
# 爬取所有页面
python run.py crawl

# 限制爬取 1000 个页面
python run.py crawl -n 1000

# 限制运行 1 小时
python run.py crawl -t 3600
```

### 4. 构建索引

```bash
python run.py index
```

### 5. 计算 PageRank

```bash
python run.py pagerank
```

### 6. 启动 Web 服务

```bash
python run.py web
```

然后访问 http://localhost:8080 使用搜索界面。

### 7. 查看统计

```bash
python run.py stats
```

## 核心算法详解

### BM25 排序算法

BM25（Best Matching 25）是概率检索模型的经典算法：

```
Score(D, Q) = Σ IDF(q_i) * (f(q_i, D) * (k1 + 1)) / (f(q_i, D) + k1 * (1 - b + b * |D| / avgdl))
```

参数说明：
- `k1 = 1.5`：词频饱和参数，控制词频增长曲线
- `b = 0.75`：文档长度归一化参数

### PageRank 算法

基于"随机冲浪者模型"的链接权威度计算：

```
PR(p_i) = (1 - d) / N + d * Σ(PR(p_j) / L(p_j))
```

参数说明：
- `d = 0.85`：阻尼因子
- 使用幂迭代法求解，收敛阈值 1e-6

### 倒排索引压缩

采用可变字节编码（Variable Byte Encoding）压缩倒排列表：
- 每个字节 7 位数据 + 1 位续位标记
- 小整数只需 1 字节，大整数用多字节
- 相比固定 4 字节存储，节省 60-80% 空间

## 配置说明

主要配置项位于 `config.py`：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `max_concurrent_requests` | 50 | 最大并发请求数 |
| `max_per_host` | 3 | 每主机最大并发数 |
| `politeness_delay` | 1.0 | 同主机请求间隔（秒） |
| `max_depth` | 10 | 最大爬取深度 |
| `bm25_k1` | 1.5 | BM25 词频饱和参数 |
| `bm25_b` | 0.75 | BM25 文档长度归一化参数 |
| `damping_factor` | 0.85 | PageRank 阻尼因子 |
| `respect_robots_txt` | True | 是否遵守 robots.txt |

## DN42 网络范围

爬虫严格限制在 dn42 网络范围内：

- **IPv4**：`172.20.0.0/14`
- **IPv6**：`fd00::/8` (ULA)
- **域名**：`.dn42`, `.dn42.dev`

如需调整，修改 `config.py` 中的 `DN42_CONFIG`。

## API 接口

### 搜索 API

```
GET /api/search?q=query&limit=20&offset=0&mode=hybrid
```

参数：
- `q`：查询关键词
- `limit`：返回结果数（默认 20，最大 100）
- `offset`：偏移量
- `mode`：排序模式（hybrid/relevance/authority）

响应：
```json
{
  "query": "搜索词",
  "results": [
    {
      "doc_id": "...",
      "url": "https://...",
      "title": "页面标题",
      "snippet": "摘要...",
      "score": {
        "final": 0.95,
        "bm25": 12.34,
        "pagerank": 0.00123
      }
    }
  ],
  "total": 100,
  "time_ms": 15
}
```

### 统计 API

```
GET /api/stats
```

### 得分解释 API

```
GET /api/explain?q=query&doc_id=xxx
```

## 性能优化建议

### 爬虫优化

1. **增加并发**：根据网络带宽调整 `max_concurrent_requests`
2. **DNS 缓存**：使用本地 DNS 缓存减少解析延迟
3. **连接复用**：已内置 HTTP 连接池
4. **增量爬取**：使用 ETag 和 Last-Modified 避免重复下载

### 索引优化

1. **分段索引**：大数据集使用多段索引 + 合并
2. **内存映射**：大索引使用 mmap 减少内存占用
3. **词干提取**：启用词干提取减少词项数量
4. **停用词过滤**：过滤高频低信息词

### 搜索优化

1. **查询缓存**：对热门查询添加缓存层（如 Redis）
2. **结果缓存**：缓存 Top 100 结果
3. **提前终止**：按评分阈值提前终止评分计算
4. **跳表索引**：倒排列表添加跳表加速交集计算

## 分布式扩展

### 多节点爬虫

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  爬虫节点 1  │  │  爬虫节点 2  │  │  爬虫节点 N  │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
       └────────────────┼────────────────┘
                        ▼
               ┌────────────────┐
               │  任务调度中心   │
               │  (Redis/队列)   │
               └────────┬───────┘
                        │
                        ▼
               ┌────────────────┐
               │  共享数据库     │
               └────────────────┘
```

### 分布式索引

参考 Elasticsearch 的分片架构：
- 按文档 ID 哈希分片
- 查询扇出到所有分片，聚合结果
- 副本分片提供高可用

## 与其他 dn42 服务集成

### Whois 数据库

可以从 dn42 registry 自动发现新域名：

```python
# 从 git 仓库拉取注册表
# git clone https://git.dn42.dev/dn42/registry.git
# 解析 data/dns/ 目录下的域名注册
```

### DNS 系统

利用 dn42 的 DNS 系统发现更多服务域名：

- 遍历 `.dn42` 子域名
- 利用反向 DNS 发现主机

### BGP 路由数据

从路由收集器获取前缀信息，扩展 IP 范围。

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

## 参考资源

- [dn42 官方 Wiki](https://wiki.dn42/)
- [The Anatomy of a Large-Scale Hypertextual Web Search Engine (Brin & Page, 1998)](https://snap.stanford.edu/class/cs224w-readings/Brin98Anatomy.pdf)
- [Introduction to Information Retrieval (Manning et al.)](https://nlp.stanford.edu/IR-book/)
- [YaCy - 分布式 P2P 搜索引擎](https://yacy.net/)
