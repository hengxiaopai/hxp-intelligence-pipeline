# HXP Intelligence Pipeline Runbook

## 1. 环境要求

- Python 3.11+
- Git
- 仅在显式实时采集时需要外网

```bash
python -m pip install -r requirements-dev.txt
```

## 2. 验证仓库

```bash
python scripts/validate.py --examples
python scripts/source_registry.py --validate
python scripts/validate_candidate.py
python scripts/validate_daily_run.py --run-dir data/daily/2026-07-29
python -m unittest discover -s tests -v
```

验证覆盖 Schema、来源策略、离线采集、候选规范化、3/7/30 天去重、编辑评分、日报组装、运行包哈希、调度计划、历史提交和失败脱敏。

## 3. 数据目录

```text
data/
├── daily/YYYY-MM-DD/
│   ├── raw/
│   ├── candidates/
│   ├── sources/
│   ├── candidate-pool.json
│   ├── editorial-scores.json
│   ├── briefing.json
│   ├── briefing.md
│   ├── run.json
│   ├── editorial-review.md
│   └── manifest.json
├── failures/
└── state/
    ├── source-watermarks.json
    └── dedup-index.json
```

## 4. 每日运行流程

### Step 0：生成来源计划

```bash
python scripts/plan_daily_run.py \
  --now "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --mode plan_only \
  --output /tmp/daily-plan.json
```

计划根据来源优先级、最小采集间隔、最大时效和失败重试时间决定当日来源。默认不访问外网。

显式实时采集：

```bash
python scripts/plan_daily_run.py \
  --now "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --mode live \
  --live-enabled \
  --output /tmp/daily-plan.json

python scripts/execute_collection_plan.py \
  --plan /tmp/daily-plan.json \
  --output-dir data/daily/YYYY-MM-DD/raw
```

`manual_only` 来源仍进入人工复核，不会被RSS/HTML执行器访问。

### Step 1：采集与来源核验

单一注册来源也可以直接采集：

```bash
python scripts/collect.py \
  --registry-id <registry-id> \
  --live \
  --output-dir data/daily/YYYY-MM-DD/raw/<source>
```

政策、金融、财务和安全主题必须优先补充官方原始来源；社媒只能作为线索。

### Step 2：候选规范化

实体、动作和对象必须显式提供，程序不会从标题自动猜测语义。

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
  --output data/daily/YYYY-MM-DD/candidates/candidate-001.json
```

### Step 3：3/7/30 天去重预判

```bash
python scripts/dedup_candidate.py \
  --candidate data/daily/YYYY-MM-DD/candidates/candidate-001.json \
  --index data/state/dedup-index.json \
  --decision-output data/daily/YYYY-MM-DD/candidates/candidate-001.dedup.json \
  --updated-index-output /tmp/dedup-index.next.json
```

- 3 天内同一事件默认淘汰；
- 7 天内同主题同观点必须提供实质 `new_delta`；
- 30 天内重复标题和视觉概念必须改写；
- 此阶段只预览，不使用 `--apply` 修改正式历史。

### Step 4：形成候选池

使用 `automation/chatgpt-daily-task.md`，把候选、来源和去重决策整理为 `candidate-pool.json`。

候选池必须显式包含事实、证据、去重动作、评分输入、公开文案、内容机会、产品门槛、风险提醒和周主线。自动化任务不直接决定最终入选顺序，也不直接生图。

### Step 5：生成每日运行包

```bash
python scripts/run_daily_pipeline.py \
  --run-dir data/daily/YYYY-MM-DD \
  --mode archived_real_sources \
  --review-status pending
```

该命令会：

1. 校验来源与候选引用；
2. 运行两次评分确认确定性；
3. 组装 5–8 条新增事实和最多 2 条延续跟踪；
4. 生成评分、JSON简报和公开Markdown；
5. 检查公开文本不包含内部淘汰池；
6. 计算所有输入输出SHA-256；
7. 写入 `run.json`。

合格候选不足时保留实际数量并填写 `shortfall_reason`。

### Step 6：验证与重放

```bash
python scripts/validate_daily_run.py \
  --run-dir data/daily/YYYY-MM-DD
```

验证器检查文件存在性、哈希、Schema、跨文件引用、公开Markdown安全，并在临时目录逐字节重放评分和组装。

### Step 7：人工编辑审核

重点检查：

- 日期、公司、产品、数字和适用范围；
- 政策是否仍在讨论、征求意见或传闻阶段；
- 业绩预告是否明确“未经审计”；
- `new_delta` 是否真是今天新增；
- 产品机会是否满足用户、痛点、付费、7天MVP和差异化；
- A股内容是否带“不构成投资建议”。

默认状态：

```json
{
  "review_status": "pending",
  "publication_allowed": false
}
```

批准后重新生成：

```bash
python scripts/run_daily_pipeline.py \
  --run-dir data/daily/YYYY-MM-DD \
  --mode archived_real_sources \
  --review-status approved
```

### Step 8：提交正式来源水位和去重历史

先预览：

```bash
python scripts/commit_daily_history.py \
  --run-dir data/daily/YYYY-MM-DD
```

预览默认写入：

```text
data/state/source-watermarks.next.json
data/state/dedup-index.next.json
data/daily/YYYY-MM-DD/history-commit.json
```

复核后应用：

```bash
python scripts/commit_daily_history.py \
  --run-dir data/daily/YYYY-MM-DD \
  --apply
```

只有 `status=validated`、`review_status=approved`、`publication_allowed=true` 且全部验证通过时才能应用。所有计算和Schema校验完成后才原子替换文件；重复执行不会重复添加 `item_id`。

### Step 9：视觉生产

只有批准且历史提交无冲突后才能进入视觉阶段：

1. 图片模型生成无文字主视觉；
2. HTML/SVG模板排版中文、数字、Logo和来源；
3. 默认导出2160×3840的9:16海报；
4. 每条信息一张图，最后一张为实际数量总览图；
5. 不固定写“今日7大焦点”。

### Step 10：质量检查与归档

使用 `prompts/quality-checker.md` 并写入 `manifest.json`。

- 内容错误：退回候选或编辑阶段；
- 中文、数字、Logo或布局错误：只重排文字层；
- 主视觉不合格：只重做视觉资产；
- 单项最多自动重试2次；
- 仍失败则人工复核，不发布错误资产。

## 5. 失败报告

```bash
python scripts/write_failure_report.py \
  --stage collection \
  --error-type CollectionError \
  --message "<sanitized-or-raw-error>" \
  --source-registry-id <registry-id>
```

脚本会清理Bearer、Token、API Key、密码、Cookie、Session和URL凭据，按失败指纹执行冷却。报告本身不自动创建Issue。

## 6. GitHub Actions

### Schema Validation

`.github/workflows/schema-validation.yml`：

- 不访问外网；
- 校验全部Schema、示例、生产状态和首份真实来源运行；
- 运行离线测试；
- 跑通采集、规范化、去重、评分和组装；
- 使用固定时间生成两次计划并比较；
- 验证待审核运行无法推进正式历史；
- 验证失败信息脱敏；
- 重新生成示例和日报确认无差异。

### HXP Daily Pipeline Plan

`.github/workflows/daily-pipeline.yml` 每天北京时间09:00执行。默认只生成计划Artifact。

- 实时采集需要 `HXP_LIVE_COLLECTION_ENABLED=true` 或手动勾选；
- 失败Issue需要 `HXP_FAILURE_ISSUES_ENABLED=true` 或手动勾选；
- 工作流不更新正式历史、不自动生图、不自动发布。

## 7. 常见失败

### 新增事实少于5条

保留实际数量并填写 `shortfall_reason`，不要补低价值条目。

### 内容机会引用未入选候选

调整 `related_candidate_ids`，只能引用正式入选的新事实或延续跟踪。

### 高风险主题进入人工复核

补充直接证据，或降低置信度并移入风险提醒/淘汰池，不能靠提高评分绕过来源门槛。

### 运行包哈希不一致

文件在生成清单后被修改。重新核验事实，再运行 `run_daily_pipeline.py` 更新输出和哈希。

### 历史提交被拒绝

检查 `review_status`、`publication_allowed`、验证结果，以及正式条目在当前去重索引中是否仍可作为新增或延续跟踪。

### 重放结果不一致

检查权重、排序兜底、集合顺序、动态时间和随机逻辑。每日运行必须使用结构化输入中的固定 `generated_at`。

## 8. 发布门槛

只有同时满足以下条件才能进入视觉与发布阶段：

- Schema和跨文件引用通过；
- 来源完整可追溯；
- 高风险事实已复核；
- 3/7/30天去重完成；
- 编辑评分和入选理由可解释；
- 文件哈希与重放通过；
- 公开内容不含内部淘汰池；
- `review_status=approved` 且 `publication_allowed=true`；
- 正式历史提交成功；
- 图片与正文数字一致；
- Logo、日期、编号和布局通过质检；
- A股内容包含“不构成投资建议”。
