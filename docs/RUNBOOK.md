# HXP Intelligence Pipeline Runbook

## 1. 环境要求

- Python 3.11+
- Git
- 能访问所需信息源的网络环境

安装校验依赖：

```bash
python -m pip install -r requirements-dev.txt
```

## 2. 验证仓库自带示例

```bash
python scripts/validate.py --examples
```

成功时应看到：

```text
PASS schema: data/examples/briefing.example.json
PASS schema: data/examples/source.example.json
PASS schema: data/examples/manifest.example.json
PASS semantics: examples are internally consistent
```

该命令同时检查：

- 三个 JSON Schema 本身是否合法；
- 示例数据是否符合 Schema；
- `actual_new_item_count` 与条目数量是否一致；
- 主来源是否包含在 `source_ids`；
- `source_index` 是否覆盖全部来源；
- 条目、事件指纹、内容机会、资产 ID 和文件名是否重复；
- 产品机会 verdict 与分数、7 天 MVP 条件是否一致；
- Manifest 数量统计和跨文件引用是否一致。

## 3. 校验单个文件

```bash
python scripts/validate.py \
  --schema schemas/briefing.schema.json \
  --data data/2026-07-29/briefing.json
```

来源文件：

```bash
python scripts/validate.py \
  --schema schemas/source.schema.json \
  --data data/2026-07-29/source-01.json
```

资产清单：

```bash
python scripts/validate.py \
  --schema schemas/manifest.schema.json \
  --data data/2026-07-29/manifest.json
```

## 4. 每日运行流程

### Step 1：运行 ChatGPT 自动化任务

使用 `automation/chatgpt-daily-task.md` 中的正式提示词，输出：

- 公开中文简报；
- `briefing.json`；
- 来源记录；
- 内部淘汰池。

自动化阶段不直接生成正式海报。

### Step 2：保存原始交付物

建议目录：

```text
data/
└── YYYY-MM-DD/
    ├── briefing.json
    ├── sources/
    │   ├── source-01.json
    │   └── source-02.json
    ├── editorial-review.md
    └── manifest.json
```

### Step 3：运行 Schema 与语义校验

先校验 `briefing.json`，再逐个校验来源记录。任何失败都必须修复，不得跳过后进入视觉阶段。

### Step 4：人工编辑审核

重点检查：

- 日期、名称、数字和时间状态；
- 政策是否仍处于讨论或征求意见阶段；
- 业绩预告是否被误写成正式财报；
- 是否存在最近 3 天事件重复、7 天观点重复；
- 产品机会是否满足真实用户、重复痛点、付费信号和 7 天 MVP 门槛；
- 是否包含不适合公开发布的内部淘汰信息。

### Step 5：视觉生产

通过审核后，使用 `prompts/visual-generator.md`：

1. 图片模型只生成无文字主视觉或背景；
2. 固定 HTML/SVG 模板排版中文、数字、Logo 和来源；
3. 默认输出 2160×3840 的 9:16 海报；
4. 每条信息一张图，最后一张为实际数量的总览图；
5. 不得固定写“今日 7 大焦点”，必须按实际条目数量生成。

### Step 6：质量检查与归档

使用 `prompts/quality-checker.md` 检查，并写入 `manifest.json`。

失败处理：

- 内容错误：退回编辑阶段；
- 中文、数字、Logo 或布局错误：只重排文字层；
- 主视觉不合格：只重做视觉资产；
- 单项最多自动重试 2 次；
- 仍失败则标记人工复核，不发布错误资产。

## 5. GitHub Actions

`.github/workflows/schema-validation.yml` 会在以下情况自动运行：

- 向 `main` 推送与 Schema、示例或校验器相关的变更；
- Pull Request 修改相关文件；
- 手动触发 `workflow_dispatch`。

CI 依次执行：

1. 安装 Python 3.12；
2. 安装 `requirements-dev.txt`；
3. 编译 `scripts/validate.py`；
4. 运行全部示例和跨文件检查。

## 6. 常见失败

### `actual_new_item_count` 不一致

修正 `editorial_policy.actual_new_item_count`，使其等于 `new_items` 实际数量。

### 新增事实少于 5 条

保留实际数量，并填写 `shortfall_reason`。不要补充低价值条目。

### `source_index` 缺少来源

将每条情报引用的全部 `source_ids` 汇总到顶层 `source_index`。

### `primary_source_id` 不在 `source_ids`

将主来源加入该条目的 `source_ids`，或者重新选择主来源。

### Manifest 数量不一致

重新统计资产总数和 `passed`、`failed` 数量。`needs_retry` 不计入 `failed`，但必须进入后续重试队列。

## 7. 发布门槛

只有同时满足以下条件，日报才允许进入发布阶段：

- Schema 校验通过；
- 来源完整可追溯；
- 高风险事实已复核；
- 去重检查完成，或明确标注去重基线缺失；
- 正式公开内容不含内部淘汰池；
- 图片与正文数字完全一致；
- Logo、日期、编号和布局通过质检；
- A 股内容包含“不构成投资建议”。
