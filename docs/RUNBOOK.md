# HXP Intelligence Pipeline Runbook

## 1. 环境要求

- Python 3.11+
- Git
- 仅在显式实时采集时需要外网

安装 Python 依赖：

```bash
python -m pip install -r requirements-dev.txt
```

Linux 进行正式 PNG 导出时，还需要系统渲染组件和 CJK 字体：

```bash
sudo apt-get install -y libcairo2 libpango-1.0-0 fonts-noto-cjk
```

仓库不保存或分发字体文件。

## 2. 验证仓库

```bash
python scripts/validate.py --examples
python scripts/source_registry.py --validate
python scripts/validate_candidate.py
python scripts/validate_daily_run.py --run-dir data/daily/2026-07-29
python -m unittest discover -s tests -v
```

验证覆盖：

- Schema 与示例数据；
- 来源策略与采集安全；
- 候选规范化和 3/7/30 天去重；
- 编辑评分与日报组装；
- 运行包哈希、调度、历史提交和失败脱敏；
- 视觉队列、中文换行、SVG、PNG、尺寸和 Manifest。

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
│   └── visual/
│       ├── queue.json
│       ├── manifest.json
│       └── posters/
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

`manual_only` 来源仍进入人工复核，不会被 RSS / HTML 执行器自动访问。

### Step 1：采集与来源核验

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

候选池必须包含事实、证据、去重动作、评分输入、公开文案、内容机会、产品门槛、风险提醒和周主线。自动化任务不直接决定最终入选顺序，也不直接生图。

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
4. 生成评分、JSON 简报和公开 Markdown；
5. 检查公开文本不包含内部淘汰池；
6. 计算所有输入输出 SHA-256；
7. 写入 `run.json`。

合格候选不足时保留实际数量并填写 `shortfall_reason`。

### Step 6：验证与重放

```bash
python scripts/validate_daily_run.py \
  --run-dir data/daily/YYYY-MM-DD
```

验证器检查文件存在性、哈希、Schema、跨文件引用、公开 Markdown 安全，并在临时目录逐字节重放评分和组装。

### Step 7：人工编辑审核

重点检查：

- 日期、公司、产品、数字和适用范围；
- 政策是否仍在讨论、征求意见或传闻阶段；
- 业绩预告是否明确“未经审计”；
- `new_delta` 是否真是今天新增；
- 产品机会是否满足用户、痛点、付费、7 天 MVP 和差异化；
- A 股内容是否带“不构成投资建议”。

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

复核后应用：

```bash
python scripts/commit_daily_history.py \
  --run-dir data/daily/YYYY-MM-DD \
  --apply
```

只有 `status=validated`、`review_status=approved`、`publication_allowed=true` 且全部验证通过时才能应用。所有计算和 Schema 校验完成后才原子替换文件；重复执行不会重复添加 `item_id`。

### Step 9：准备正式视觉资产

正式 Logo 建议路径：

```text
assets/brand/hengxiaopai-logo-approved.svg
```

主视觉按 `item_id` 命名：

```text
visual-input/YYYY-MM-DD/
├── item-YYYYMMDD-01.png
├── item-YYYYMMDD-02.png
└── ...
```

图片模型只生成无文字主视觉。中文、数字、Logo、日期、编号和来源由固定模板排版。不得伪造产品截图、财务图表、官方 UI、合作关系或统计数字。

### Step 10：创建视觉任务队列

```bash
python scripts/build_visual_queue.py \
  --run-dir data/daily/YYYY-MM-DD \
  --logo assets/brand/hengxiaopai-logo-approved.svg \
  --visual-dir visual-input/YYYY-MM-DD \
  --output data/daily/YYYY-MM-DD/visual/queue.json
```

硬性条件：

- `run.status=validated`
- `run.review_status=approved`
- `run.publication_allowed=true`
- 正式 Logo 存在
- 每条详情海报主视觉存在

CI 或内部预览可使用 `--allow-placeholder`，但会生成 `preview_only=true`，不得公开发布。

### Step 11：渲染 SVG 与 PNG

```bash
python scripts/render_posters.py \
  --queue data/daily/YYYY-MM-DD/visual/queue.json \
  --output-dir data/daily/YYYY-MM-DD/visual/posters \
  --manifest data/daily/YYYY-MM-DD/visual/manifest.json
```

输出规则：

- 每条正式情报一张 2160×3840 详情海报；
- 最后一张为实际条目数量总览图；
- 不固定写“今日 7 大焦点”；
- SVG 是母版，PNG 是发布资产；
- 缺少中文字体、Logo、主视觉或出现文本溢出时返回失败。

### Step 12：视觉质检与归档

```bash
python scripts/validate_visual_assets.py \
  --queue data/daily/YYYY-MM-DD/visual/queue.json \
  --manifest data/daily/YYYY-MM-DD/visual/manifest.json
```

质检包括：

- Queue 与 Manifest Schema；
- SVG / PNG 哈希、字节数和精确尺寸；
- Logo、主视觉、日期、编号、标题与来源；
- 中文文本溢出；
- 正式资产不得使用测试 Logo 或占位主视觉；
- Manifest 汇总统计。

失败处理：

- 内容错误：退回候选或编辑阶段；
- 中文、数字、Logo 或布局错误：只重排文字层；
- 主视觉不合格：只重做对应主视觉；
- 单项最多自动重试 2 次；
- 仍失败则人工复核，不发布错误资产。

## 5. 失败报告

```bash
python scripts/write_failure_report.py \
  --stage collection \
  --error-type CollectionError \
  --message "<sanitized-or-raw-error>" \
  --source-registry-id <registry-id>
```

脚本会清理 Bearer、Token、API Key、密码、Cookie、Session 和 URL 凭据，按失败指纹执行冷却。报告本身不自动创建 Issue。

## 6. GitHub Actions

### Schema Validation

`.github/workflows/schema-validation.yml`：

- 不访问外部内容源；
- 校验全部 Schema、示例、生产状态和首份真实来源运行；
- 运行所有离线单元测试；
- 跑通采集、规范化、去重、评分和组装；
- 验证待审核运行无法推进正式历史；
- 验证失败信息脱敏；
- 使用测试 Logo 和明确标记的占位主视觉生成 5 张详情海报与 1 张总览海报；
- 验证 6 张 SVG、6 张 2160×3840 PNG 与视觉 Manifest；
- 上传 `hxp-visual-preview-2026-07-29` Artifact；
- 重新生成示例和日报确认无差异。

### HXP Daily Pipeline Plan

`.github/workflows/daily-pipeline.yml` 每天北京时间 09:00 执行。默认只生成计划 Artifact。

- 实时采集需要 `HXP_LIVE_COLLECTION_ENABLED=true` 或手动勾选；
- 失败 Issue 需要 `HXP_FAILURE_ISSUES_ENABLED=true` 或手动勾选；
- 工作流不更新正式历史、不自动生图、不自动发布。

## 7. 常见失败

### 新增事实少于 5 条

保留实际数量并填写 `shortfall_reason`，不要补低价值条目。

### 内容机会引用未入选候选

调整 `related_candidate_ids`，只能引用正式入选的新事实或延续跟踪。

### 高风险主题进入人工复核

补充直接证据，或降低置信度并移入风险提醒/淘汰池，不能靠提高评分绕过来源门槛。

### 运行包哈希不一致

文件在生成清单后被修改。重新核验事实，再运行 `run_daily_pipeline.py` 更新输出和哈希。

### 历史提交被拒绝

检查 `review_status`、`publication_allowed`、验证结果，以及正式条目在当前去重索引中是否仍可作为新增或延续跟踪。

### 视觉队列被拒绝

检查是否已批准、是否允许发布、正式 Logo 是否存在，以及全部详情主视觉是否按 `item_id` 命名。

### PNG 导出失败

检查 Cairo、Pango、CairoSVG、Pillow 和系统 CJK 字体。仓库不会提供字体文件。

### 视觉质检失败

按照 Manifest 中的 `errors` 定向修复：文本错误只重排，视觉错误只重做主视觉，不要整体盲目重生。

## 8. 发布门槛

只有同时满足以下条件才能进入正式发布：

- Schema 和跨文件引用通过；
- 来源完整可追溯；
- 高风险事实已复核；
- 3/7/30 天去重完成；
- 编辑评分和入选理由可解释；
- 文件哈希与重放通过；
- 公开内容不含内部淘汰池；
- `review_status=approved` 且 `publication_allowed=true`；
- 正式历史提交成功；
- 正式 Logo 和每条主视觉存在；
- SVG 与 PNG 尺寸、哈希和文本通过；
- 无占位符、无文本溢出；
- 图片与正文数字一致；
- A 股内容包含“不构成投资建议”。
