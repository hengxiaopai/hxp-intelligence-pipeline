# HXP Intelligence Pipeline Runbook

## 1. 环境要求

- Python 3.11+
- Git
- 能访问所需信息源的网络环境

安装依赖：

```bash
python -m pip install -r requirements-dev.txt
```

## 2. 验证仓库

```bash
python scripts/validate.py --examples
python scripts/source_registry.py --validate
python scripts/validate_candidate.py
python -m unittest discover -s tests -v
```

该流程检查：

- Schema 与示例数据；
- 来源注册策略；
- 候选与来源引用；
- RSS / HTML 离线采集；
- 候选规范化和 3/7/30 天去重；
- 编辑评分、确定性排序和日报组装；
- 内容机会、产品机会、内部淘汰池和跨字段引用。

## 3. 每日目录

```text
data/
└── YYYY-MM-DD/
    ├── raw/
    ├── candidates/
    ├── sources/
    ├── candidate-pool.json
    ├── editorial-scores.json
    ├── briefing.json
    ├── briefing.md
    ├── editorial-review.md
    └── manifest.json
```

## 4. 每日运行流程

### Step 1：采集与来源核验

通过来源注册表和采集器生成原始快照。实时访问必须显式使用 `--live`，并遵守 `docs/COLLECTORS.md` 的安全边界。

```bash
python scripts/collect.py \
  --registry-id <registry-id> \
  --live \
  --output-dir data/YYYY-MM-DD/raw/<source>
```

政策、金融、财务和安全主题优先补充官方原始来源；单一社媒线索不能直接进入正式简报。

### Step 2：候选规范化

原始条目必须显式提供实体、动作和对象，不允许程序从标题自动猜测事件语义。

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
  --output data/YYYY-MM-DD/candidates/candidate-001.json
```

### Step 3：3/7/30 天去重

```bash
python scripts/dedup_candidate.py \
  --candidate data/YYYY-MM-DD/candidates/candidate-001.json \
  --index data/dedup/index.json \
  --decision-output data/YYYY-MM-DD/candidates/candidate-001.dedup.json \
  --updated-index-output /tmp/dedup-index.next.json
```

规则：

- 3 天内同一事件默认淘汰；
- 7 天内同主题同观点必须提供实质 `new_delta`；
- 30 天内重复标题和视觉概念必须改写；
- 只有日报正式采用后，才使用 `--apply` 更新历史索引。

### Step 4：形成候选池

使用 `automation/chatgpt-daily-task.md` 的任务提示词，结合候选、来源和去重决策，生成 `candidate-pool.json`。

候选池必须显式包含：

- 事实与证据；
- 去重动作和新颖性类型；
- 编辑评分输入；
- 公开标题、摘要、为什么重要和后续关注；
- 内容机会、产品机会门槛、风险提醒和周主线。

自动化任务不直接决定最终入选顺序，也不直接生成海报。

### Step 5：编辑评分

```bash
python scripts/score_candidates.py \
  --pool data/YYYY-MM-DD/candidate-pool.json \
  --output data/YYYY-MM-DD/editorial-scores.json
```

校验：

```bash
python scripts/validate.py \
  --schema schemas/editorial-score.schema.json \
  --data data/YYYY-MM-DD/editorial-scores.json
```

评分包含来源权威、时效、相关性、证据、影响、新颖性、内容价值、产品价值和风险扣分。

### Step 6：日报组装

```bash
python scripts/assemble_briefing.py \
  --pool data/YYYY-MM-DD/candidate-pool.json \
  --scores data/YYYY-MM-DD/editorial-scores.json \
  --output data/YYYY-MM-DD/briefing.json \
  --markdown data/YYYY-MM-DD/briefing.md
```

组装器负责：

- 目标 5–8 条，不为凑数降级；
- 至少 60% 为新主题或新角度；
- 延续跟踪最多 2 条；
- 分类软平衡；
- 产品机会五项门槛；
- 来源索引和引用映射；
- 内部淘汰池；
- A 股公开 Markdown 风险提示。

校验：

```bash
python scripts/validate.py \
  --schema schemas/briefing.schema.json \
  --data data/YYYY-MM-DD/briefing.json
```

### Step 7：人工编辑审核

重点检查：

- 日期、公司名、产品名、数字和时间状态；
- 政策是否仍处于讨论、征求意见或传闻阶段；
- 业绩预告是否明确“未经审计”；
- `new_delta` 是否真的是今天新增变化；
- 产品机会是否满足用户、痛点、付费、7 天 MVP 和差异化门槛；
- 公开 Markdown 是否未包含内部淘汰池；
- A 股内容是否带“不构成投资建议”。

任何事实错误都必须退回候选或编辑阶段，不能在视觉阶段掩盖。

### Step 8：视觉生产

通过审核后，使用 `prompts/visual-generator.md`：

1. 图片模型只生成无文字主视觉或背景；
2. 固定 HTML/SVG 模板排版中文、数字、Logo 和来源；
3. 默认输出 2160×3840 的 9:16 海报；
4. 每条信息一张图，最后一张为实际数量的总览图；
5. 不得固定写“今日 7 大焦点”。

### Step 9：质量检查与归档

使用 `prompts/quality-checker.md` 检查并写入 `manifest.json`。

失败处理：

- 内容错误：退回候选或编辑阶段；
- 中文、数字、Logo 或布局错误：只重排文字层；
- 主视觉不合格：只重做视觉资产；
- 单项最多自动重试 2 次；
- 仍失败则标记人工复核，不发布错误资产。

## 5. GitHub Actions

`.github/workflows/schema-validation.yml` 在 main、Pull Request 和手动触发时执行：

1. 编译采集、规范化、去重、评分和组装代码；
2. 校验全部 Schema 和示例；
3. 运行离线单元测试；
4. 跑通 Snapshot → Candidate → Dedup；
5. 跑通 Candidate Pool → Score → Briefing → Markdown；
6. 重新生成示例并确认 Git 差异为零。

CI 不访问外网。

## 6. 常见失败

### 新增事实少于 5 条

保留实际数量并填写 `shortfall_reason`。不要补充低价值条目。

### 内容机会引用未入选候选

调整内容机会的 `related_candidate_ids`，只能引用正式入选的新事实或延续跟踪。

### 高风险主题进入人工复核

补充直接证据，或降低置信度并移入风险提醒/淘汰池。不得通过提高编辑分数绕过来源门槛。

### 延续跟踪无法通过 Schema

确认包含 `previous_item_ids`、不少于 12 字的 `new_delta`，且 `background_repeated=false`。

### 示例生成后出现 Git 差异

说明评分或组装结果不再确定。检查权重、排序兜底、日期和集合输出顺序。

## 7. 发布门槛

只有同时满足以下条件，日报才允许进入发布阶段：

- Schema 校验通过；
- 来源完整可追溯；
- 高风险事实已复核；
- 3/7/30 天去重完成；
- 编辑评分和入选理由可解释；
- 正式公开内容不含内部淘汰池；
- 图片与正文数字完全一致；
- Logo、日期、编号和布局通过质检；
- A 股内容包含“不构成投资建议”。
