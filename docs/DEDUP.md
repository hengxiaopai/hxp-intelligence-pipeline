# HXP Normalization & Dedup

## 目标

去重系统不是简单比较标题，而是分别处理五类重复：

1. **事件重复**：同一主体、动作、对象与事件日期；
2. **主题重复**：不同事件仍围绕同一实体与对象；
3. **观点重复**：标题不同，但摘要和判断高度相似；
4. **标题重复**：内容可能不同，但传播标题结构被重复使用；
5. **视觉重复**：海报持续使用相同构图、隐喻或主视觉。

系统输出可解释决策，不自动伪装新角度，也不依赖大模型黑箱相似度。

## 规范化边界

`pipeline/normalization.py` 只处理确定性差异：

- Unicode NFKC 与全半角；
- 英文大小写；
- 标点和空白；
- 已登记实体别名；
- 实体排列顺序。

它不会从标题擅自推断事件动作、对象、因果或影响。`scripts/normalize_candidate.py` 要求操作者显式提供：

- `--entity`；
- `--action`；
- `--object`；
- `--primary-category`；
- `--information-type`。

这样可以避免把宣传文案或歧义标题直接转换为事实。

## 稳定事件指纹

事件指纹由以下字段生成：

```text
canonical_entities（排序后）
+ event_action
+ event_object
+ event_date
```

序列化采用稳定键顺序，再计算 SHA-256：

```text
evt-<32 hex chars>
```

以下写法应产生相同指纹：

- `GitHub` / `git hub`；
- `Dependabot` / `dependa bot`；
- 英文大小写变化；
- 中文或英文标点变化；
- 实体输入顺序变化。

事件日期属于指纹的一部分。同一发布被不同媒体在次日报道时，仍应保留原始事件日期，而不是转载日期。

## 3/7/30 天规则

### 3 天：事件窗口

事件指纹一致且距离历史记录不超过 3 天：

- 无 `new_delta`：`reject_duplicate_event`；
- 有可审核的新变化：`continuation`。

`new_delta` 必须说明今天新增的事实、数据、功能、回应或影响，不能只是改写背景。

### 7 天：主题与观点窗口

主题指纹由类别、实体和事件对象生成，不包含日期。若 7 天内主题一致，再比较摘要观点：

- 观点指纹相同，或文本相似度达到阈值：无新增变化时拒绝；
- 有新增变化：进入延续跟踪；
- 主题相同但观点差异足够大：允许作为新角度进入编辑审核。

中英文混合文本使用拉丁词元、中文双字词和序列相似度共同判断。

### 30 天：内容资产窗口

30 天内标题或视觉概念重复，不直接拒绝事件，但产生强制警告：

- `title_reuse_warning=true`：必须重写标题；
- `visual_reuse_warning=true`：必须更换构图、视角或视觉隐喻。

该规则防止每天都是“芯片 + 蓝色立方体 + 上升箭头”，也防止选题标题只替换公司名称。

## 候选规范化命令

先生成快照：

```bash
python scripts/collect.py \
  --registry-id registry-arxiv-cs-ai \
  --input-file tests/fixtures/arxiv-cs-ai.xml \
  --output-dir /tmp/hxp-rss
```

再把一个快照条目转为候选：

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
  --output /tmp/candidate.json
```

规范化命令会：

- 读取实体别名；
- 生成稳定事件指纹；
- 计算来源权威与时效分数；
- 创建证据引用；
- 保留原始快照哈希、路径和解析器版本；
- 按 `candidate.schema.json` 校验后写出。

## 去重命令

首次运行可使用不存在的索引路径，脚本会在内存中建立空索引：

```bash
python scripts/dedup_candidate.py \
  --candidate /tmp/candidate.json \
  --index data/dedup/index.json \
  --decision-output /tmp/decision.json \
  --updated-index-output /tmp/index.json \
  --apply
```

连续热点需要显式提供新增变化：

```bash
python scripts/dedup_candidate.py \
  --candidate /tmp/candidate.json \
  --index data/dedup/index.json \
  --decision-output /tmp/decision.json \
  --new-delta "官方新增了企业部署数据，并公布了迁移限制。"
```

## 决策结果

| 决策 | 含义 | 索引处理 |
|---|---|---|
| `select_new` | 新事件或新角度，可进入编辑审核 | 创建记录 |
| `continuation` | 连续热点，只写新增变化 | 更新同事件或创建新事件记录 |
| `reject_duplicate_event` | 3 天内同一事件，无新增变化 | 不更新 |
| `reject_duplicate_viewpoint` | 7 天内同主题同观点，无新角度 | 不更新 |
| `manual_review` | 规则无法安全判断 | 暂不自动入选 |

去重只判断重复，不替代事实核验。低置信度、政策讨论、未经审计财务数据和安全敏感内容仍需编辑审核。

## 测试

```bash
python -m unittest discover -s tests -v
```

测试覆盖：

- 全半角、大小写和标点规范化；
- 实体别名与顺序稳定性；
- 事件指纹确定性；
- 3 天事件拒绝与延续跟踪；
- 7 天主题观点去重；
- 30 天标题与视觉警告；
- 资产窗口到期后的正常放行。
