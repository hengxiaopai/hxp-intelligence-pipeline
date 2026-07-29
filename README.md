# HXP Intelligence Pipeline

珩小派多元情报采集、审核、海报生成与资产归档流水线。

## 项目目标

将每日情报生产拆成可追溯、可重放且默认不自动发布的流程：

1. **计划与采集**：按来源优先级、最小间隔和最大时效生成采集计划。
2. **审核与组装**：事实核验、3/7/30 天去重、编辑评分和日报组装。
3. **人工批准**：自动校验通过后仍保持待审核，批准后才能推进正式历史。
4. **视觉与归档**：AI 生成无文字主视觉，固定模板排版中文并完成质检。

## 核心原则

- 不为凑数引入低价值信息；每日合格焦点目标为 5–8 条。
- 连续热点只记录可证实的新增变化。
- 政策、金融、财务、安全等内容优先使用官方或一手来源。
- 评分、排序、入选、淘汰和历史提交都必须可解释、可重放。
- 实时采集、失败 Issue、历史推进和正式发布全部默认关闭或受显式闸门约束。
- **AI 生视觉，模板排文字**，不依赖图片模型渲染大段中文。

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
│   ├── schedule.json
│   └── sources.json
├── data/
│   ├── daily/2026-07-29/
│   ├── examples/
│   └── state/
│       ├── dedup-index.json
│       └── source-watermarks.json
├── docs/
│   ├── COLLECTORS.md
│   ├── DAILY-RUN.md
│   ├── DEDUP.md
│   ├── EDITORIAL-ASSEMBLY.md
│   ├── RUNBOOK.md
│   ├── SCHEDULING.md
│   ├── SOURCE-REGISTRY.md
│   └── VISUAL-SPEC.md
├── pipeline/
│   ├── briefing_assembler.py
│   ├── dedup.py
│   ├── editorial_scoring.py
│   ├── failure_reporting.py
│   ├── history_commit.py
│   ├── normalization.py
│   └── scheduler.py
├── schemas/
│   ├── briefing.schema.json
│   ├── candidate.schema.json
│   ├── daily-plan.schema.json
│   ├── daily-run.schema.json
│   ├── dedup-decision.schema.json
│   ├── dedup-index.schema.json
│   ├── editorial-score.schema.json
│   ├── failure-report.schema.json
│   ├── manifest.schema.json
│   ├── raw-snapshot.schema.json
│   ├── schedule-state.schema.json
│   ├── source-registry.schema.json
│   └── source.schema.json
├── scripts/
│   ├── assemble_briefing.py
│   ├── collect.py
│   ├── commit_daily_history.py
│   ├── dedup_candidate.py
│   ├── execute_collection_plan.py
│   ├── generate_daily_run_20260729.py
│   ├── normalize_candidate.py
│   ├── plan_daily_run.py
│   ├── run_daily_pipeline.py
│   ├── score_candidates.py
│   ├── validate_daily_run.py
│   ├── validate.py
│   └── write_failure_report.py
├── tests/
│   ├── fixtures/
│   ├── test_collectors.py
│   ├── test_daily_run.py
│   ├── test_editorial_assembly.py
│   ├── test_normalization_dedup.py
│   └── test_scheduler_history.py
└── .github/workflows/
    ├── daily-pipeline.yml
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

## 1. 生成每日来源计划

```bash
python scripts/plan_daily_run.py \
  --now 2026-07-29T01:00:00Z \
  --mode plan_only \
  --output /tmp/daily-plan.json
```

计划读取来源注册表和 `data/state/source-watermarks.json`，按优先级、最小间隔、最大时效和失败重试时间确定应处理来源。

实时采集必须显式使用 `--mode live --live-enabled`；GitHub 定时工作流还要求仓库变量 `HXP_LIVE_COLLECTION_ENABLED=true`。默认计划不访问外网。

## 2. 候选、去重与日报组装

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
  --index data/state/dedup-index.json \
  --decision-output /tmp/decision.json \
  --updated-index-output /tmp/index.next.json

python scripts/run_daily_pipeline.py \
  --run-dir data/daily/2026-07-29 \
  --mode archived_real_sources \
  --review-status pending

python scripts/validate_daily_run.py \
  --run-dir data/daily/2026-07-29
```

运行包记录来源、候选、评分、简报、公开 Markdown、SHA-256、验证状态和人工审核状态。

## 3. 人工批准后提交正式历史

待审核运行禁止推进水位和去重历史：

```bash
python scripts/commit_daily_history.py \
  --run-dir data/daily/2026-07-29 \
  --apply
```

上面的命令对当前归档运行会按设计失败，因为它仍是 `review_status=pending`。

审核通过后，先重新生成批准状态，再预览和应用：

```bash
python scripts/run_daily_pipeline.py \
  --run-dir data/daily/YYYY-MM-DD \
  --mode archived_real_sources \
  --review-status approved

python scripts/commit_daily_history.py \
  --run-dir data/daily/YYYY-MM-DD

python scripts/commit_daily_history.py \
  --run-dir data/daily/YYYY-MM-DD \
  --apply
```

历史提交是原子的、幂等的，同一 `item_id` 不会重复进入正式索引。

## 4. 定时任务与失败告警

`.github/workflows/daily-pipeline.yml` 每天北京时间 09:00 运行。默认只生成计划并上传 Artifact，不自动提交内容、不更新历史、不生图、不发布。

失败报告会清理 Authorization、Bearer、Token、API Key、密码、Cookie 和 Session。自动创建 GitHub Issue 仍需显式启用 `HXP_FAILURE_ISSUES_ENABLED=true`，并按失败指纹去重。

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
- 调度、水位与历史：[`docs/SCHEDULING.md`](docs/SCHEDULING.md)
- 来源注册策略：[`docs/SOURCE-REGISTRY.md`](docs/SOURCE-REGISTRY.md)
- 采集安全边界：[`docs/COLLECTORS.md`](docs/COLLECTORS.md)
- 规范化与去重：[`docs/DEDUP.md`](docs/DEDUP.md)
- 编辑评分与组装：[`docs/EDITORIAL-ASSEMBLY.md`](docs/EDITORIAL-ASSEMBLY.md)
- 视觉规范：[`docs/VISUAL-SPEC.md`](docs/VISUAL-SPEC.md)

## 当前阶段

- Phase 1.1：核心数据 Schema ✅
- Phase 1.2：六 Agent Prompt Engine ✅
- Phase 1.3：示例、校验、CI 与自动化入口 ✅
- Phase 2.1：官方来源注册表与候选池 ✅
- Phase 2.2：RSS / HTML 采集与原始快照 ✅
- Phase 2.3：稳定指纹与 3/7/30 天去重 ✅
- Phase 3.1：编辑评分与日报组装器 ✅
- Phase 3.2：首份真实每日运行包 ✅
- Phase 3.3：按日调度、增量水位、历史提交与失败告警 🚧
- Phase 4：固定模板海报、中文排版与视觉队列 ⏳
