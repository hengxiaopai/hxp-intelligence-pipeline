# HXP Intelligence Pipeline

珩小派多元情报采集、审核、海报生成与资产归档流水线。

## 项目目标

将每日多元情报生产拆成可追溯的四阶段流程：

1. **采集**：发现信号，保存来源、时间与证据。
2. **审核**：事实核验、3/7/30 天去重、编辑评分与日报组装。
3. **视觉**：AI 生成无文字主视觉，固定模板完成中文排版。
4. **质检归档**：校验文字、数字、Logo、来源、哈希与发布状态。

## 核心原则

- 不为凑数引入低价值信息；每日合格焦点目标为 5–8 条。
- 连续热点只记录可证实的新增变化。
- 政策、金融、财务、安全等内容优先使用官方或一手来源。
- 评分、排序、入选和淘汰都必须可解释、可重放。
- **AI 生视觉，模板排文字**，不依赖图片模型渲染大段中文。
- 自动校验通过不等于允许发布；人工审核状态必须单独记录。

## 当前结构

```text
hxp-intelligence-pipeline/
├── automation/
│   └── chatgpt-daily-task.md
├── collectors/
│   ├── base.py
│   ├── html_index.py
│   ├── rss.py
│   └── snapshot.py
├── config/
│   ├── daily-run.json
│   ├── editorial-weights.json
│   ├── entity-aliases.json
│   └── sources.json
├── data/
│   ├── daily/
│   │   └── 2026-07-29/
│   └── examples/
├── docs/
│   ├── COLLECTORS.md
│   ├── DAILY-RUN.md
│   ├── DEDUP.md
│   ├── EDITORIAL-ASSEMBLY.md
│   ├── RUNBOOK.md
│   ├── SOURCE-REGISTRY.md
│   └── VISUAL-SPEC.md
├── pipeline/
│   ├── briefing_assembler.py
│   ├── dedup.py
│   ├── editorial_scoring.py
│   └── normalization.py
├── schemas/
│   ├── briefing.schema.json
│   ├── candidate.schema.json
│   ├── daily-run.schema.json
│   ├── dedup-decision.schema.json
│   ├── dedup-index.schema.json
│   ├── editorial-score.schema.json
│   ├── manifest.schema.json
│   ├── raw-snapshot.schema.json
│   ├── source-registry.schema.json
│   └── source.schema.json
├── scripts/
│   ├── assemble_briefing.py
│   ├── collect.py
│   ├── dedup_candidate.py
│   ├── generate_daily_run_20260729.py
│   ├── normalize_candidate.py
│   ├── run_daily_pipeline.py
│   ├── score_candidates.py
│   ├── validate_daily_run.py
│   └── validate.py
├── tests/
│   ├── fixtures/
│   ├── test_collectors.py
│   ├── test_daily_run.py
│   ├── test_editorial_assembly.py
│   └── test_normalization_dedup.py
└── .github/workflows/
    └── schema-validation.yml
```

## 快速验证

```bash
python -m pip install -r requirements-dev.txt
python scripts/validate.py --examples
python scripts/source_registry.py --validate
python scripts/validate_candidate.py
python scripts/validate_daily_run.py --run-dir data/daily/2026-07-29
python -m unittest discover -s tests -v
```

## 流水线

### 1. 采集原始快照

```bash
python scripts/collect.py \
  --registry-id registry-arxiv-cs-ai \
  --input-file tests/fixtures/arxiv-cs-ai.xml \
  --output-dir /tmp/hxp-rss
```

实时访问必须显式传入 `--live`，并受来源白名单、HTTPS、DNS、robots、重定向、MIME、响应大小和超时限制。

### 2. 规范化和去重

```bash
python scripts/normalize_candidate.py \
  --snapshot <snapshot.json> \
  --source <source.json> \
  --item-index 0 \
  --sequence 1 \
  --entity "<entity>" \
  --action "<action>" \
  --object "<object>" \
  --primary-category <category> \
  --information-type <type> \
  --output /tmp/candidate.json

python scripts/dedup_candidate.py \
  --candidate /tmp/candidate.json \
  --index data/dedup/index.json \
  --decision-output /tmp/decision.json \
  --updated-index-output /tmp/index.next.json
```

### 3. 编辑评分和日报组装

```bash
python scripts/score_candidates.py \
  --pool data/examples/candidate-pool.example.json \
  --output /tmp/editorial-scores.json

python scripts/assemble_briefing.py \
  --pool data/examples/candidate-pool.example.json \
  --scores /tmp/editorial-scores.json \
  --output /tmp/briefing.json \
  --markdown /tmp/briefing.md
```

### 4. 生成完整每日运行包

```bash
python scripts/run_daily_pipeline.py \
  --run-dir data/daily/2026-07-29 \
  --mode archived_real_sources \
  --review-status pending

python scripts/validate_daily_run.py \
  --run-dir data/daily/2026-07-29
```

运行包记录输入、输出、来源文件 SHA-256、Schema 状态、引用完整性、公开 Markdown 安全检查和确定性重放结果。

## 首份真实来源日报

`data/daily/2026-07-29/` 已归档首份端到端运行：

- 6 个已核对的一手官方来源；
- 7 个候选事件；
- 5 条今日新增事实；
- 2 条内部淘汰候选；
- 评分、简报、Markdown 与运行清单全部通过校验；
- `review_status=pending`，因此 `publication_allowed=false`。

## 文档

- 总运行手册：[`docs/RUNBOOK.md`](docs/RUNBOOK.md)
- 每日运行包：[`docs/DAILY-RUN.md`](docs/DAILY-RUN.md)
- 来源注册策略：[`docs/SOURCE-REGISTRY.md`](docs/SOURCE-REGISTRY.md)
- 采集安全边界：[`docs/COLLECTORS.md`](docs/COLLECTORS.md)
- 规范化与去重：[`docs/DEDUP.md`](docs/DEDUP.md)
- 编辑评分与组装：[`docs/EDITORIAL-ASSEMBLY.md`](docs/EDITORIAL-ASSEMBLY.md)
- 视觉规范：[`docs/VISUAL-SPEC.md`](docs/VISUAL-SPEC.md)

## 自动化入口

[`automation/chatgpt-daily-task.md`](automation/chatgpt-daily-task.md) 输出结构化候选池。程序再执行确定性评分、组装、校验和人工审核；正式海报只读取审核通过的数据。

## 当前阶段

- Phase 1.1：核心数据 Schema ✅
- Phase 1.2：六 Agent Prompt Engine ✅
- Phase 1.3：示例、校验、CI 与自动化入口 ✅
- Phase 2.1：官方来源注册表与候选池 ✅
- Phase 2.2：RSS / HTML 采集与原始快照 ✅
- Phase 2.3：稳定指纹与 3/7/30 天去重 ✅
- Phase 3.1：编辑评分与日报组装器 ✅
- Phase 3.2：首份真实每日运行包 ✅
- Phase 3.3：按日调度、增量历史与失败告警 ⏳
