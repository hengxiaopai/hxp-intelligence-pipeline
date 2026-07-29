# HXP Intelligence Pipeline Runbook

## 1. 环境要求

- Python 3.11+
- Git
- 仅在实时采集阶段需要可访问来源的网络环境

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

验证覆盖 Schema、来源策略、离线采集、候选规范化、3/7/30 天去重、编辑评分、日报组装、运行包哈希与确定性重放。

## 3. 每日目录

```text
data/daily/YYYY-MM-DD/
├── raw/                       # 可选：网页或Feed快照
├── candidates/                # 可选：独立候选和去重决策
├── sources/                   # 必须：结构化来源记录
├── candidate-pool.json        # 必须：候选池
├── editorial-scores.json      # 自动生成
├── briefing.json              # 自动生成，含内部淘汰记录
├── briefing.md                # 自动生成，公开版
├── run.json                   # 自动生成，哈希与审核状态
├── editorial-review.md        # 人工审核记录
└── manifest.json              # 视觉阶段生成
```

## 4. 每日运行流程

### Step 1：采集与来源核验

通过来源注册表生成原始快照。实时访问必须显式使用 `--live`，并遵守 `docs/COLLECTORS.md`。

```bash
python scripts/collect.py \
  --registry-id <registry-id> \
  --live \
  --output-dir data/daily/YYYY-MM-DD/raw/<source>
```

政策、金融、财务和安全主题优先补充官方原始来源；社媒只能作为线索。

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

### Step 3：3/7/30 天去重

```bash
python scripts/dedup_candidate.py \
  --candidate data/daily/YYYY-MM-DD/candidates/candidate-001.json \
  --index data/dedup/index.json \
  --decision-output data/daily/YYYY-MM-DD/candidates/candidate-001.dedup.json \
  --updated-index-output /tmp/dedup-index.next.json
```

- 3 天内同一事件默认淘汰；
- 7 天内同主题同观点必须提供实质 `new_delta`；
- 30 天内重复标题和视觉概念必须改写；
- 只有日报正式采用后，才可用 `--apply` 更新历史索引。

### Step 4：形成候选池

使用 `automation/chatgpt-daily-task.md`，把候选、来源和去重决策整理为 `candidate-pool.json`。

候选池必须显式包含：

- 事实、来源和证据声明；
- 去重动作与新颖性类型；
- 编辑评分输入；
- 公开标题、摘要、为什么重要和后续关注；
- 内容机会、产品门槛、风险提醒和周主线。

自动化任务不直接决定最终入选顺序，也不直接生图。

### Step 5：生成每日运行包

推荐使用统一入口，而不是分别手动调用评分和组装：

```bash
python scripts/run_daily_pipeline.py \
  --run-dir data/daily/YYYY-MM-DD \
  --mode archived_real_sources \
  --review-status pending
```

该命令执行：

1. 校验所有来源记录和候选引用；
2. 对同一候选池运行两次评分，确认结果一致；
3. 组装 5–8 条新增事实和最多 2 条延续跟踪；
4. 生成 `editorial-scores.json`、`briefing.json` 和 `briefing.md`；
5. 检查公开 Markdown 不包含内部候选与淘汰池；
6. 计算所有输入输出文件 SHA-256；
7. 写入 `run.json`。

合格候选不足时保留实际数量并填写 `shortfall_reason`，禁止补充低价值新闻。

### Step 6：验证与重放

```bash
python scripts/validate_daily_run.py \
  --run-dir data/daily/YYYY-MM-DD
```

验证器检查：

- `daily-run.schema.json`；
- 文件存在性、SHA-256 和字节数；
- 来源、候选、评分和简报 Schema；
- source_id、candidate_id 与 item_id 引用；
- 公开 Markdown 安全；
- 临时目录重放后的评分、简报和 Markdown 是否逐字节一致。

### Step 7：人工编辑审核

重点检查：

- 日期、公司名、产品名、数字和适用范围；
- 政策是否仍处于讨论、征求意见或传闻阶段；
- 业绩预告是否明确“未经审计”；
- `new_delta` 是否真的是今天新增变化；
- 产品机会是否满足用户、痛点、付费、7 天 MVP 和差异化；
- 公开 Markdown 是否未包含内部淘汰池；
- A 股内容是否带“不构成投资建议”。

默认运行状态：

```json
{
  "review_status": "pending",
  "publication_allowed": false
}
```

审核通过后重新生成清单：

```bash
python scripts/run_daily_pipeline.py \
  --run-dir data/daily/YYYY-MM-DD \
  --mode archived_real_sources \
  --review-status approved
```

任何事实错误必须退回候选或编辑阶段，不能在视觉阶段掩盖。

### Step 8：视觉生产

只有 `publication_allowed=true` 才能进入视觉阶段：

1. 图片模型生成无文字主视觉；
2. HTML/SVG 模板排版中文、数字、Logo 和来源；
3. 默认导出 2160×3840 的 9:16 海报；
4. 每条信息一张图，最后一张为实际数量总览图；
5. 不固定写“今日 7 大焦点”。

### Step 9：质量检查与归档

使用 `prompts/quality-checker.md` 并写入 `manifest.json`。

- 内容错误：退回候选或编辑阶段；
- 中文、数字、Logo 或布局错误：只重排文字层；
- 主视觉不合格：只重做视觉资产；
- 单项最多自动重试 2 次；
- 仍失败则人工复核，不发布错误资产。

## 5. GitHub Actions

`.github/workflows/schema-validation.yml` 在 main、Pull Request 和手动触发时：

1. 编译采集、规范化、去重、评分、组装和日报运行代码；
2. 校验全部 Schema、示例和首份真实来源运行；
3. 运行所有离线单元测试；
4. 跑通 Snapshot → Candidate → Dedup；
5. 跑通 Candidate Pool → Score → Briefing → Markdown；
6. 重放 `data/daily/2026-07-29/`；
7. 重新生成示例和日报，确认 Git 差异为零。

CI 不访问外网，也不自动发布。

## 6. 常见失败

### 新增事实少于 5 条

保留实际数量并填写 `shortfall_reason`，不要补充低价值条目。

### 内容机会引用未入选候选

调整 `related_candidate_ids`，只能引用正式入选的新事实或延续跟踪。

### 高风险主题进入人工复核

补充直接证据，或降低置信度并移入风险提醒/淘汰池。不能靠提高编辑分数绕过来源门槛。

### 运行包哈希不一致

说明文件在生成清单后被修改。重新核验事实，再运行 `run_daily_pipeline.py` 更新输出和哈希。

### 重放结果不一致

检查权重、排序兜底、集合输出顺序、动态时间和随机逻辑。每日运行必须使用结构化输入中的固定 `generated_at`。

### `publication_allowed` 意外为 true

确认 `review_status`。自动校验通过不代表人工审核通过。

## 7. 发布门槛

只有同时满足以下条件，日报才允许进入视觉与发布阶段：

- Schema 校验通过；
- 来源完整可追溯；
- 高风险事实已复核；
- 3/7/30 天去重完成；
- 编辑评分和入选理由可解释；
- 文件哈希与重放检查通过；
- 正式公开内容不含内部淘汰池；
- `review_status=approved` 且 `publication_allowed=true`；
- 图片与正文数字完全一致；
- Logo、日期、编号和布局通过质检；
- A 股内容包含“不构成投资建议”。
