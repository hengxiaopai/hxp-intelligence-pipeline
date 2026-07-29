# 编辑评分与日报组装

Phase 3.1 将已经完成来源核验与去重的候选事件，确定性地转换为《珩小派多元情报简报》。本阶段不负责抓取网页，也不允许根据标题擅自补写事实。

## 输入

`data/examples/candidate-pool.example.json` 展示了候选池交接格式。每个条目包含三部分：

1. `candidate`：符合 `schemas/candidate.schema.json` 的事实与证据记录；
2. `dedup`：去重动作、新颖性类型、历史匹配和可证实 `new_delta`；
3. `editorial`：编辑评分、公开文案、受众、转化方向和主视觉约束。

内容机会、产品机会、风险提醒和本周主线在候选池顶层显式提供。组装器只做校验、映射和排序，不从候选标题自动臆测这些字段。

## 评分模型

评分配置位于 `config/editorial-weights.json`。

默认分值由以下维度加权：

- 来源权威度；
- 时效性；
- 与珩小派关注范围的相关性；
- 证据质量；
- 产业或产品影响；
- 新颖性；
- 内容转化价值；
- 产品化价值。

风险项在加权结果之后扣减，且总扣分设有上限。评分输出符合 `schemas/editorial-score.schema.json`，包含各维度、最终分数、准入状态、建议动作和解释原因。

## 准入规则

### 新增事实

- 达到 `select_new` 分数线；
- 置信度不能为 `low`；
- 去重结论不能是重复事件或无新增变化；
- `novelty_kind` 必须为 `new_theme` 或 `new_angle`；
- 高风险主题必须至少拥有一条直接证据。

每日目标为 5–8 条。合格候选不足时保留实际数量并填写 `shortfall_reason`，禁止为了数量降低质量门槛。

### 延续跟踪

- 最多 2 条；
- 必须由去重层给出 `track_continuation`；
- 必须提供历史 `previous_item_ids`；
- 必须提供不少于 12 个字符的实质 `new_delta`；
- 正式输出只写新增变化，不重复历史背景。

### 栏目平衡

组装器使用分类软上限，避免单一栏目占满日报。软上限不会制造虚假短缺：当合格条目足够但类别集中时，仍会按分数补足最低目标。

### 产品机会

产品机会通过五项门槛判断：

1. 用户明确；
2. 痛点重复出现；
3. 存在付费信号；
4. 7 天可以完成 MVP；
5. 存在差异化。

至少四项通过才输出 `build`；两到三项为 `observe`；否则为 `reject`。没有任何入选事实支撑时，产品机会自动降为空值。

## 运行

生成评分报告：

```bash
python scripts/score_candidates.py \
  --pool data/examples/candidate-pool.example.json \
  --output /tmp/editorial-scores.json
```

组装 JSON 和公开 Markdown：

```bash
python scripts/assemble_briefing.py \
  --pool data/examples/candidate-pool.example.json \
  --scores /tmp/editorial-scores.json \
  --output /tmp/briefing.json \
  --markdown /tmp/briefing.md
```

校验：

```bash
python scripts/validate.py \
  --schema schemas/editorial-score.schema.json \
  --data /tmp/editorial-scores.json

python scripts/validate.py \
  --schema schemas/briefing.schema.json \
  --data /tmp/briefing.json
```

## 输出边界

- `briefing.json` 可以包含内部 `rejected_candidates`，用于审计选择结果；
- `render_markdown()` 不输出内部淘汰池；
- A 股条目存在时，公开 Markdown 固定添加“不构成投资建议”；
- 正式海报仍需在数据审核通过后，由视觉阶段读取结构化数据生成；
- 图片模型只生成无文字主视觉，中文、数字、Logo 和来源由固定模板排版。

## 确定性

在候选池、去重结果和权重配置不变时：

- 各候选分数不变；
- 排序以最终分数降序、候选 ID 升序作为稳定兜底；
- 生成的条目编号、来源索引、内容机会引用和淘汰原因保持一致。

这使日报结果可以回测、比较和审计，而不是依赖一次性模型发挥。
