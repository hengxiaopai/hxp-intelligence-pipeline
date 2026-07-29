# HXP Source Registry

## 目标

`config/sources.json` 是所有情报采集入口的唯一注册表。Collector 不得绕过注册表临时抓取未知站点，也不得把榜单、社区帖子或设计图库默认视为官方事实。

注册表解决五个问题：

1. 这个来源是谁发布的；
2. 它属于官方证据、可靠补充还是线索；
3. 应采用 RSS、HTML、API 还是人工复核；
4. 多久检查一次，允许使用多旧的信息；
5. 该来源最容易造成什么误判。

## 权威等级

### Tier 1：`tier_1_official`

适用于：

- 大厂官方 Newsroom、Changelog 和开发者文档；
- 论文原始页面；
- 交易所与上市公司公告；
- 正式监管文件。

Tier 1 代表来源身份可靠，不代表其所有判断都无需分析。例如 arXiv 是论文原始来源，但预印本仍可能未经同行评审。

### Tier 2：`tier_2_reliable_media`

适用于权威媒体、行业数据库和具有编辑审核机制的研究机构。Tier 2 可用于交叉验证，但高风险结论仍应回到原始来源。

### Tier 3：`tier_3_signal_only`

适用于：

- GitHub Trending；
- Product Hunt 排名；
- Hugging Face 社区文章；
- Awwwards 等设计趋势平台；
- 社媒与社区讨论。

Tier 3 只能证明“出现了传播或兴趣信号”，不能直接证明产品成功、收入增长、技术领先或投资价值。

## 采集方式

| 方式 | 含义 | 当前策略 |
|---|---|---|
| `rss` | 官方或稳定 Feed | 可低频自动获取元数据 |
| `html_index` | 官方列表页或 Changelog | 先解析列表，再打开原文核验 |
| `api` | 官方 API | 必须遵守认证、配额和条款 |
| `manual_review` | 人工搜索与核验 | 不进行高频自动访问 |

`access_policy` 是硬约束：

- `respect_robots_and_terms`：遵守 robots、服务条款和合理频率；
- `manual_only`：只允许人工或浏览器辅助复核；
- `official_api_only`：禁止 HTML 抓取，只能使用官方 API。

## 首批来源组合

当前注册表覆盖：

- AI 大厂：OpenAI、Anthropic、Google AI；
- 开发者工具：GitHub Changelog；
- 开源信号：GitHub Trending、Hugging Face、arXiv；
- 产品趋势：Product Hunt；
- A 股披露：巨潮资讯、上海证券交易所、深圳证券交易所；
- 设计灵感：Awwwards。

A 股入口以公告发现为主。任何经营数字、订单、利润、客户与产能结论，都必须打开公司原始公告或 PDF 再确认。

## 注册表命令

验证 Schema 与策略：

```bash
python scripts/source_registry.py --validate
```

列出全部启用来源：

```bash
python scripts/source_registry.py --list --active-only
```

只查看最高优先级来源：

```bash
python scripts/source_registry.py --list --active-only --max-priority 1
```

查看开发者工具来源：

```bash
python scripts/source_registry.py \
  --list \
  --active-only \
  --category developer_tools
```

输出给 Collector 使用的结构化采集计划：

```bash
python scripts/source_registry.py \
  --emit-plan \
  --active-only \
  --max-priority 3
```

该命令不会访问网络，只生成安全的执行计划。

## 从来源到候选事件

```text
Source Registry
      ↓
Discovery / Fetch Adapter
      ↓
Raw Snapshot
      ↓
Candidate Event
      ↓
Dedup Agent
      ↓
Editorial Reviewer
      ↓
Briefing Item
```

Collector 输出必须符合 `schemas/candidate.schema.json`，并包含：

- 规范化实体、动作、对象和事件日期；
- 稳定事件指纹；
- 每个事实主张对应的来源证据；
- 权威、时效与相关度评分；
- 原始快照哈希和解析器版本；
- 初步风险标记。

候选事件只代表“值得审核”，不代表已经入选正式简报。

## 来源新增流程

新增来源时必须：

1. 确认发布主体和官方 URL；
2. 选择正确的权威等级与内容范围；
3. 评估 robots、服务条款、登录与频率限制；
4. 填写 `risk_notes`；
5. 运行 Registry Schema 与语义检查；
6. 通过 Pull Request 审核后启用。

禁止：

- 为了补足数量临时加入未知聚合站；
- 把转载页面当作原始来源；
- 对 `manual_only` 来源启用自动高频抓取；
- 使用无授权的付费墙绕过、账号共享或反爬规避；
- 把平台热度直接转换为商业成功或投资结论。
