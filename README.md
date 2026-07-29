# HXP Intelligence Pipeline

珩小派多元情报采集、审核、海报生成与资产归档流水线。

## 项目目标

将每日情报生产拆成可追溯、可重放且默认不自动发布的流程：

1. **计划与采集**：按来源优先级、最小间隔和最大时效生成采集计划。
2. **审核与组装**：事实核验、3/7/30 天去重、编辑评分和日报组装。
3. **人工批准**：自动校验通过后仍保持待审核，批准后才能推进正式历史与视觉阶段。
4. **视觉与归档**：AI 生成无文字主视觉，固定 SVG 模板排版中文、导出 PNG 并完成质检。

## 核心原则

- 不为凑数引入低价值信息；每日合格焦点目标为 5–8 条。
- 连续热点只记录可证实的新增变化。
- 政策、金融、财务、安全等内容优先使用官方或一手来源。
- 评分、排序、入选、淘汰、历史提交和视觉资产都必须可解释、可重放。
- 实时采集、失败 Issue、历史推进和正式发布全部默认关闭或受显式闸门约束。
- **AI 生视觉，模板排文字**，不依赖图片模型渲染大段中文。
- 仓库不保存或分发字体文件；正式 Logo 必须使用主理人批准的品牌资产。

## 当前结构

```text
hxp-intelligence-pipeline/
├── assets/brand/
│   └── README.md
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
│   ├── sources.json
│   └── visual-theme.json
├── data/
│   ├── daily/2026-07-29/
│   ├── examples/
│   └── state/
├── docs/
│   ├── DAILY-RUN.md
│   ├── EDITORIAL-ASSEMBLY.md
│   ├── RUNBOOK.md
│   ├── SCHEDULING.md
│   ├── VISUAL-PIPELINE.md
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
│   ├── dedup-index.schema.json
│   ├── failure-report.schema.json
│   ├── visual-manifest.schema.json
│   └── visual-queue.schema.json
├── scripts/
│   ├── build_visual_queue.py
│   ├── collect.py
│   ├── commit_daily_history.py
│   ├── plan_daily_run.py
│   ├── render_posters.py
│   ├── run_daily_pipeline.py
│   ├── validate_daily_run.py
│   ├── validate_visual_assets.py
│   └── write_failure_report.py
├── visual/
│   ├── layout.py
│   ├── pipeline.py
│   ├── queue.py
│   ├── rasterizer.py
│   └── svg_renderer.py
├── tests/
│   ├── fixtures/hxp-test-logo.svg
│   ├── fixtures/visual-placeholder.svg
│   └── test_visual_pipeline.py
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

Linux PNG 导出还需要系统组件和 CJK 字体：

```bash
sudo apt-get install -y libcairo2 libpango-1.0-0 fonts-noto-cjk
```

## 1. 生成每日来源计划

```bash
python scripts/plan_daily_run.py \
  --now 2026-07-29T01:00:00Z \
  --mode plan_only \
  --output /tmp/daily-plan.json
```

默认计划不访问外网。实时采集必须显式使用 `--mode live --live-enabled`，GitHub 定时工作流还要求仓库变量 `HXP_LIVE_COLLECTION_ENABLED=true`。

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
  --run-dir data/daily/YYYY-MM-DD \
  --mode archived_real_sources \
  --review-status pending
```

运行包记录来源、候选、评分、简报、公开 Markdown、SHA-256、验证状态和人工审核状态。

## 3. 人工批准与历史提交

待审核运行禁止推进正式水位、去重历史和视觉资产：

```bash
python scripts/commit_daily_history.py \
  --run-dir data/daily/2026-07-29 \
  --apply
```

该命令对当前归档运行会按设计失败，因为它仍是 `review_status=pending`。

审核通过后重新生成批准状态，再预览和应用历史：

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

## 4. 固定模板海报

准备已批准 Logo 和按 `item_id` 命名的无文字主视觉后，创建任务队列：

```bash
python scripts/build_visual_queue.py \
  --run-dir data/daily/YYYY-MM-DD \
  --logo assets/brand/hengxiaopai-logo-approved.svg \
  --visual-dir visual-input/YYYY-MM-DD \
  --output data/daily/YYYY-MM-DD/visual/queue.json
```

渲染 2160×3840 SVG 与 PNG：

```bash
python scripts/render_posters.py \
  --queue data/daily/YYYY-MM-DD/visual/queue.json \
  --output-dir data/daily/YYYY-MM-DD/visual/posters \
  --manifest data/daily/YYYY-MM-DD/visual/manifest.json

python scripts/validate_visual_assets.py \
  --queue data/daily/YYYY-MM-DD/visual/queue.json \
  --manifest data/daily/YYYY-MM-DD/visual/manifest.json
```

每条正式情报生成一张详情海报，最后生成一张按实际数量汇总的总览海报。缺少正式 Logo、主视觉、中文字体或存在文本溢出时，正式渲染硬阻断。

CI 使用测试 Logo 和明确标记的占位主视觉生成 **5 张详情预览 + 1 张总览预览**，Artifact 名称为 `hxp-visual-preview-2026-07-29`。这些预览不得公开发布。

## 5. 定时任务与失败告警

`.github/workflows/daily-pipeline.yml` 每天北京时间 09:00 运行。默认只生成计划并上传 Artifact，不自动提交内容、不更新历史、不生图、不发布。

失败报告会清理 Authorization、Bearer、Token、API Key、密码、Cookie 和 Session。自动创建 GitHub Issue 仍需显式启用 `HXP_FAILURE_ISSUES_ENABLED=true`。

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
- 调度与历史：[`docs/SCHEDULING.md`](docs/SCHEDULING.md)
- 编辑评分与组装：[`docs/EDITORIAL-ASSEMBLY.md`](docs/EDITORIAL-ASSEMBLY.md)
- 视觉生产：[`docs/VISUAL-PIPELINE.md`](docs/VISUAL-PIPELINE.md)
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
- Phase 3.3：按日调度、增量水位、历史提交与失败告警 ✅
- Phase 4.1：固定 SVG 海报、中文排版、PNG 导出与视觉队列 🚧
- Phase 4.2：AI 主视觉生成、批量重试与多平台尺寸 ⏳
