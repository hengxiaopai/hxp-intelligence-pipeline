# HXP Intelligence Pipeline

珩小派多元情报采集、审核、海报生成与资产归档流水线。

## 项目目标

将每日多元情报生产拆成可追溯的四阶段流程：

1. **采集**：抓取并结构化记录候选信号、来源与时间。
2. **审核**：事实核验、置信度分级、去重、标题提炼与风险检查。
3. **视觉**：AI 生成无文字主视觉，固定模板完成中文排版与多尺寸导出。
4. **质检归档**：校验文字、数字、Logo、来源和版式，保存 Markdown、JSON、图片与清单。

## 核心原则

- 不为凑数引入低价值信息；每日合格焦点目标为 5–8 条。
- 连续热点只记录新增变化，并标记 `continuation`。
- 政策、金融、财务、安全等内容优先使用官方或一手来源。
- **AI 生视觉，模板排文字**，避免依赖图片模型渲染大量中文。
- 所有产物可追溯到原始来源、审核记录、生成提示词与质检结果。
- 未通过 Schema、事实和视觉质检的内容不得进入发布阶段。

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
│   ├── entity-aliases.json
│   └── sources.json
├── data/
│   └── examples/
├── docs/
│   ├── ARCHITECTURE.md
│   ├── COLLECTORS.md
│   ├── CONTENT-SPEC.md
│   ├── DEDUP.md
│   ├── PROMPT-ENGINE.md
│   ├── RUNBOOK.md
│   ├── SOURCE-REGISTRY.md
│   └── VISUAL-SPEC.md
├── pipeline/
│   ├── dedup.py
│   └── normalization.py
├── prompts/
│   ├── dedup-agent.md
│   ├── editorial-reviewer.md
│   ├── intelligence-collector.md
│   ├── product-opportunity-agent.md
│   ├── quality-checker.md
│   └── visual-generator.md
├── schemas/
│   ├── briefing.schema.json
│   ├── candidate.schema.json
│   ├── dedup-decision.schema.json
│   ├── dedup-index.schema.json
│   ├── manifest.schema.json
│   ├── raw-snapshot.schema.json
│   ├── source-registry.schema.json
│   └── source.schema.json
├── scripts/
│   ├── collect.py
│   ├── dedup_candidate.py
│   ├── normalize_candidate.py
│   ├── source_registry.py
│   ├── validate.py
│   └── validate_candidate.py
├── tests/
│   ├── fixtures/
│   ├── test_collectors.py
│   └── test_normalization_dedup.py
├── .github/workflows/
│   └── schema-validation.yml
└── requirements-dev.txt
```

## 快速开始

安装依赖：

```bash
python -m pip install -r requirements-dev.txt
```

验证数据规范、来源策略和候选引用：

```bash
python scripts/validate.py --examples
python scripts/source_registry.py --validate
python scripts/validate_candidate.py
```

运行全部离线测试：

```bash
python -m unittest discover -s tests -v
```

### 1. 生成原始快照

```bash
python scripts/collect.py \
  --registry-id registry-arxiv-cs-ai \
  --input-file tests/fixtures/arxiv-cs-ai.xml \
  --output-dir /tmp/hxp-rss
```

### 2. 规范化为候选事件

```bash
SNAPSHOT=$(find /tmp/hxp-rss -name '*.json' -print -quit)

python scripts/normalize_candidate.py \
  --snapshot "$SNAPSHOT" \
  --source tests/fixtures/arxiv-source.json \
  --item-index 0 \
  --sequence 1 \
  --entity "Example Research Group" \
  --action "发布预印本" \
  --object "可审计 Agent 工作流研究" \
  --primary-category ai_technology \
  --information-type paper \
  --risk-flag unconfirmed \
  --output /tmp/hxp-candidate.json
```

### 3. 执行 3/7/30 天去重

```bash
python scripts/dedup_candidate.py \
  --candidate /tmp/hxp-candidate.json \
  --index data/dedup/index.json \
  --decision-output /tmp/hxp-decision.json \
  --updated-index-output /tmp/hxp-index.json \
  --apply
```

详细说明：

- 运行与发布流程：[`docs/RUNBOOK.md`](docs/RUNBOOK.md)
- 来源注册策略：[`docs/SOURCE-REGISTRY.md`](docs/SOURCE-REGISTRY.md)
- 采集器安全边界：[`docs/COLLECTORS.md`](docs/COLLECTORS.md)
- 规范化与去重规则：[`docs/DEDUP.md`](docs/DEDUP.md)

## 自动化入口

[`automation/chatgpt-daily-task.md`](automation/chatgpt-daily-task.md) 提供可复制到 ChatGPT Tasks 的每日情报提示词。

自动化任务负责搜索、来源核验、去重、编辑和结构化交付；正式海报必须在数据通过审核后生成。

## 当前阶段

- Phase 1.1：核心数据 Schema ✅
- Phase 1.2：六 Agent Prompt Engine ✅
- Phase 1.3：示例数据、校验脚本、CI 与自动化入口 ✅
- Phase 2.1：官方来源注册表与候选事件池 ✅
- Phase 2.2：RSS / HTML 轻量采集适配器与原始快照 ✅
- Phase 2.3：候选规范化、稳定指纹与去重索引 ✅
- Phase 3：编辑评分、日报组装与真实候选池运行 ⏳
