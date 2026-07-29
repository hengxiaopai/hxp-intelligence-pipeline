# 多平台独立模板导出

## 目标

将人工审核通过的主视觉与已批准的简报文案，分别排版为四套独立模板，而不是把 9:16 成品粗暴裁切：

| 预设 | 尺寸 | 平台 | 内容密度 |
|---|---:|---|---|
| `vertical_9x16` | 2160×3840 | 抖音、视频号 | 完整详情与总览 |
| `portrait_3x4` | 2160×2880 | 小红书 | 紧凑详情与总览 |
| `landscape_16x9` | 2560×1440 | X、YouTube、网站 | 标题、判断、主视觉 |
| `wechat_cover_235x1` | 2350×1000 | 微信公众号头图 | 封面级标题与主题视觉 |

每个预设拥有独立安全区、字号、视觉占比和信息层级。`config/export-presets.json` 明确设置 `direct_crop_from_vertical_forbidden=true`。

## 发布闸门

正式导出必须同时满足：

1. `visual-queue.json` 来自已批准且允许发布的每日运行；
2. 每个详情条目至少有一个已导入图片结果；
3. 结果通过人工审核，所有检查项均为 `true`；
4. 当同一条目存在多个尝试时，使用尝试次数最高的已批准结果；
5. Logo 文件存在；
6. 系统存在可用 CJK 字体；
7. 每个模板均无文本溢出，PNG 尺寸、文件哈希和 Manifest 一致。

事实错误不允许通过重新生成图片处理，必须退回编辑阶段。

## 输入文件

```text
visual/queue.json
visual/requests.reviewed.json
visual/review.json
config/export-presets.json
config/visual-theme.json
```

详情图绑定：

```text
item_id
  ↓
latest approved request_id
  ↓
exact asset SHA-256
  ↓
4 independent templates
```

总览图由结构化简报直接生成，不需要 AI 主视觉，因此 Manifest 中：

```json
{
  "item_id": null,
  "source_request_id": null,
  "source_asset_sha256": null,
  "review_decision": "not_applicable"
}
```

## 执行导出

```bash
python scripts/export_platform_assets.py \
  --visual-queue data/daily/YYYY-MM-DD/visual/queue.json \
  --requests data/daily/YYYY-MM-DD/visual/requests.reviewed.json \
  --review data/daily/YYYY-MM-DD/visual/review.json \
  --output-dir data/daily/YYYY-MM-DD/visual/platforms \
  --manifest data/daily/YYYY-MM-DD/visual/export-manifest.json
```

输出目录：

```text
platforms/
├── vertical_9x16/
├── portrait_3x4/
├── landscape_16x9/
└── wechat_cover_235x1/
```

每个目录同时保存 SVG 母版和 PNG 发布资产。

## 校验

```bash
python scripts/validate_platform_exports.py \
  --manifest data/daily/YYYY-MM-DD/visual/export-manifest.json
```

校验范围：

- Export Manifest Schema；
- 导出 ID 唯一性；
- 详情图的人工批准状态、请求 ID 和主视觉哈希；
- 总览图的 `not_applicable` 状态；
- SVG 与 PNG 文件存在、SHA-256 和字节数；
- SVG 画布尺寸；
- PNG 精确尺寸；
- 文本溢出和裁切安全；
- 每个预设的导出数量。

任何正式资产失败时，命令返回非零退出码。

## 设计差异

### 9:16

保留完整摘要、为什么重要、后续关注、来源和转化方向。

### 3:4

压缩为主标题、主视觉、摘要以及两张精简分析卡，适合小红书连续翻页。

### 16:9

采用左侧标题与判断、右侧主视觉的横向编辑式结构，避免竖图居中裁切造成主体丢失。

### 2.35:1

只保留品牌栏目、标题、副标题、来源和主视觉，作为公众号头图；不塞入详情正文。

## 失败处理

- `缺少人工审核通过的主视觉`：完成审核或导入最新尝试；
- `审核哈希与图片结果不一致`：禁止继续，检查是否替换过文件；
- `固定平台模板存在文本溢出`：优先重新提炼标题或摘要，不无限缩小字号；
- `PNG尺寸错误`：检查导出预设和栅格化依赖；
- `CJK字体不可用`：安装系统中文字体，仓库不分发字体文件；
- `裁切不安全`：定向重做主视觉构图，主体收回安全区域。

## 审计原则

- 不覆盖旧尝试；
- 不改变图片模型结果文件；
- 每个正式详情导出保留 `source_request_id` 与 `source_asset_sha256`；
- 每个 SVG、PNG 记录自身 SHA-256；
- 平台模板版本单独记录；
- 未审核、占位或文本溢出的资产不得进入分发阶段。
