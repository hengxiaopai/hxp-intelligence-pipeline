# 固定模板视觉流水线

## 目标

把人工审核通过的 `briefing.json` 转换为：

1. 每条正式情报一张 2160×3840 详情海报；
2. 一张按实际条目数量生成的总览海报；
3. 可追溯的视觉队列、SVG、PNG 与 Manifest。

核心原则是：

> AI 生成无文字主视觉，固定 SVG 模板排版中文、数字、Logo 和来源。

## 发布闸门

只有同时满足以下条件，才允许创建正式视觉队列：

- `run.status=validated`
- `run.review_status=approved`
- `run.publication_allowed=true`
- 所有运行验证项均为 `true`
- 已提供主理人批准的正式 Logo
- 每张详情海报已提供对应主视觉

`--allow-placeholder` 只用于 CI 或内部预览，并会把队列和 Manifest 标记为 `preview_only=true`。

## 1. 准备主视觉

主视觉目录按 `item_id` 命名：

```text
visual-input/YYYY-MM-DD/
├── item-20260729-01.png
├── item-20260729-02.png
├── item-20260729-03.png
├── item-20260729-04.png
└── item-20260729-05.png
```

主视觉不得包含大段中文，也不得伪造产品截图、财务图表、官方界面、合作关系或统计数据。

## 2. 创建视觉任务队列

```bash
python scripts/build_visual_queue.py \
  --run-dir data/daily/YYYY-MM-DD \
  --logo assets/brand/hengxiaopai-logo-approved.svg \
  --visual-dir visual-input/YYYY-MM-DD \
  --output data/daily/YYYY-MM-DD/visual/queue.json
```

队列包括：

- 日期、模板版本和 2160×3840 画布；
- 详情海报的标题、摘要、置信度、为什么重要、后续关注、来源简称；
- 总览海报的实际焦点数量、今日主线、内容机会、产品机会和风险；
- 每张图的主视觉路径与禁止伪造事项。

总览标题不会固定写“今日 7 大焦点”，而是使用实际入选数量。

## 3. 渲染 SVG 与 PNG

```bash
python scripts/render_posters.py \
  --queue data/daily/YYYY-MM-DD/visual/queue.json \
  --output-dir data/daily/YYYY-MM-DD/visual/posters \
  --manifest data/daily/YYYY-MM-DD/visual/manifest.json
```

渲染器会：

- 使用固定编辑式网格；
- 自动进行中英文显示宽度计算与换行；
- 嵌入 Logo 和主视觉；
- 输出可复用 SVG 母版；
- 使用系统 CJK 字体导出精确 2160×3840 PNG；
- 记录 SHA-256、文件大小、占位符、文本溢出和失败原因。

## 4. 视觉质检

```bash
python scripts/validate_visual_assets.py \
  --queue data/daily/YYYY-MM-DD/visual/queue.json \
  --manifest data/daily/YYYY-MM-DD/visual/manifest.json
```

质检范围：

- Queue 与 Manifest Schema；
- 任务和资产一一对应；
- SVG 与 PNG 哈希、文件大小和精确尺寸；
- Logo、主视觉、日期、编号、标题和来源；
- 中文文本溢出；
- 正式资产不得使用测试 Logo 或占位视觉；
- Manifest 统计一致性。

任何资产失败时，正式渲染命令返回非零退出码。

## 5. CI 预览

CI 会复制首份真实来源运行包，在临时目录中显式改为批准状态，并使用：

- `tests/fixtures/hxp-test-logo.svg`
- `tests/fixtures/visual-placeholder.svg`

生成 5 张详情海报与 1 张总览海报。该产物仅用于模板和中文排版验证，Artifact 名称为：

```text
hxp-visual-preview-2026-07-29
```

预览文件带有测试标识，禁止公开发布。

## 6. 字体边界

仓库不保存或分发字体文件。Linux CI 安装系统包 `fonts-noto-cjk`；Windows 和 macOS 使用系统已有字体。找不到可用 CJK 字体时，PNG 导出硬阻断，但 SVG 母版仍可单独生成用于诊断。
