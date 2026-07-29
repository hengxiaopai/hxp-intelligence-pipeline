# HXP Intelligence Pipeline

珩小派多元情报采集、审核、海报生成、内容适配与资产归档流水线。

## 项目定位

把每日情报生产拆成可追溯、可重放、默认不自动发布的生产流程：

```text
来源计划与采集
  ↓
事实核验与结构化
  ↓
3 / 7 / 30 天去重
  ↓
编辑评分与日报组装
  ↓
人工批准
  ↓
AI 无文字主视觉
  ↓
人工视觉审核与定向重试
  ↓
固定模板中文排版
  ↓
多平台独立尺寸导出
  ↓
五个平台草稿内容包
  ↓
发布计划与人工确认
  ↓
本地 HTML / Markdown 预览
  ↓
后续逐平台连接器
```

## 核心原则

- 每日目标 5–8 条高价值情报，不为凑数加入低质量信息。
- 连续热点只记录可证实的新增变化。
- 政策、金融、财务和安全主题优先使用官方或一手来源。
- 评分、去重、入选、淘汰、审核、重试、导出和发布计划必须可解释、可重放。
- 实时采集、历史推进、图片生成和正式发布均受显式闸门约束。
- **AI 生视觉，模板排文字，程序做质检，人工做最终审核。**
- 图片模型不得生成大段中文、正式 Logo、虚构 UI、财务图表或合作关系。
- 仓库不保存 API 密钥、Cookie、Authorization、私密原始响应或字体文件。
- Phase 5.1 即使人工批准，仍保持 `write_actions_enabled=false` 与 `external_write_performed=false`。

## 当前能力

### 情报与编辑

- 官方来源注册表与采集策略
- RSS / Atom 与语义化 HTML 采集
- 原始快照与来源追溯
- 稳定事件指纹
- 3 / 7 / 30 天去重
- 编辑评分与栏目平衡
- 5–8 条日报自动组装
- 内容机会、产品机会与风险提醒
- 人工批准与历史提交闸门

### 视觉生产

- 2160×3840 固定 SVG / PNG 详情与总览模板
- 中文显示宽度计算、自动换行和溢出阻断
- 稳定 AI 主视觉 Prompt 与请求指纹
- `manual_chatgpt` 人工交接
- 图片结果 SHA-256、尺寸和 MIME 绑定
- 人工事实、品牌、构图和裁切审核
- 失败条目定向重试，旧尝试不覆盖
- 最新已批准主视觉选择
- 9:16、3:4、16:9、2.35:1 四套独立平台模板
- SVG / PNG 文件哈希、尺寸和 Export Manifest 验证

### 内容适配与发布准备

- 微信公众号、小红书、抖音图文、X 与网站五个平台内容包
- 平台标题、摘要、正文、话题、线程、SEO 与来源规则
- 已验证图片的文件哈希和顺序绑定
- A 股内容风险说明闸门
- 敏感凭据、内部淘汰池和绝对收益表达阻断
- 稳定内容哈希与发布幂等键
- 平台、账号占位符、文案版本和图片顺序的明确人工确认
- 五份 HTML 与五份 Markdown 本地预览
- 仅允许 `dry_run`，不登录、不保存凭据、不写入平台

## 目录结构

```text
hxp-intelligence-pipeline/
├── assets/brand/                 # 正式品牌资产接入规范
├── automation/                   # ChatGPT 自动化任务提示词
├── collectors/                   # RSS、HTML 与快照采集
├── config/
│   ├── sources.json
│   ├── editorial-weights.json
│   ├── schedule.json
│   ├── visual-theme.json
│   ├── visual-providers.json
│   ├── export-presets.json
│   └── platform-profiles.json
├── data/
│   ├── daily/YYYY-MM-DD/
│   ├── examples/
│   └── state/
├── docs/
│   ├── RUNBOOK.md
│   ├── DAILY-RUN.md
│   ├── SCHEDULING.md
│   ├── EDITORIAL-ASSEMBLY.md
│   ├── VISUAL-PIPELINE.md
│   ├── VISUAL-SPEC.md
│   ├── AI-VISUALS.md
│   ├── MULTI-PLATFORM-EXPORT.md
│   └── PUBLISHING.md
├── pipeline/                     # 去重、评分、组装、调度和历史提交
├── publishing/
│   ├── platform_rules.py
│   ├── package_builder.py
│   ├── plan.py
│   ├── approval.py
│   └── dry_run.py
├── schemas/                      # 全部数据契约
├── scripts/                      # CLI 入口
├── visual/
│   ├── queue.py
│   ├── svg_renderer.py
│   ├── rasterizer.py
│   ├── prompt_builder.py
│   ├── request_queue.py
│   ├── result_import.py
│   ├── review.py
│   ├── retry_policy.py
│   ├── approved_assets.py
│   ├── multiformat.py
│   └── export_polish.py
└── .github/workflows/            # 离线 CI、每日计划与视觉验证
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

Linux SVG → PNG 导出需要：

```bash
sudo apt-get install -y libcairo2 libpango-1.0-0 fonts-noto-cjk
```

仓库不会提交或分发字体文件。

## 每日运行

### 1. 生成来源计划

```bash
python scripts/plan_daily_run.py \
  --now 2026-07-29T01:00:00Z \
  --mode plan_only \
  --output /tmp/daily-plan.json
```

默认不访问外网。实时采集必须显式启用。

### 2. 生成待审核日报

```bash
python scripts/run_daily_pipeline.py \
  --run-dir data/daily/YYYY-MM-DD \
  --mode archived_real_sources \
  --review-status pending
```

### 3. 人工批准与历史提交

```bash
python scripts/run_daily_pipeline.py \
  --run-dir data/daily/YYYY-MM-DD \
  --mode archived_real_sources \
  --review-status approved

python scripts/commit_daily_history.py \
  --run-dir data/daily/YYYY-MM-DD \
  --apply
```

待审核或验证失败的运行不能推进正式历史。

## 视觉生产

### 1. 创建固定模板队列

```bash
python scripts/build_visual_queue.py \
  --run-dir data/daily/YYYY-MM-DD \
  --logo assets/brand/hengxiaopai-logo-approved.svg \
  --visual-dir visual-input/YYYY-MM-DD \
  --output data/daily/YYYY-MM-DD/visual/queue.json
```

### 2. 创建无文字主视觉请求

```bash
python scripts/build_visual_requests.py \
  --visual-queue data/daily/YYYY-MM-DD/visual/queue.json \
  --provider manual_chatgpt \
  --output data/daily/YYYY-MM-DD/visual/requests.json
```

将每个请求的 Prompt 交给 ChatGPT 图片生成，并按 `request_id` 保存结果。

### 3. 导入、审核与定向重试

```bash
python scripts/import_visual_results.py \
  --requests data/daily/YYYY-MM-DD/visual/requests.json \
  --result-dir visual-results/YYYY-MM-DD \
  --generator-reference chatgpt-manual-YYYYMMDD \
  --output data/daily/YYYY-MM-DD/visual/requests.imported.json

python scripts/review_visuals.py \
  --requests data/daily/YYYY-MM-DD/visual/requests.imported.json \
  --decisions data/daily/YYYY-MM-DD/visual/review-decisions.json \
  --review-output data/daily/YYYY-MM-DD/visual/review.json \
  --requests-output data/daily/YYYY-MM-DD/visual/requests.reviewed.json

python scripts/retry_failed_visuals.py \
  --requests data/daily/YYYY-MM-DD/visual/requests.reviewed.json \
  --review data/daily/YYYY-MM-DD/visual/review.json \
  --generated-at 2026-07-29T15:10:00+08:00 \
  --plan-output data/daily/YYYY-MM-DD/visual/retry-plan.json \
  --requests-output data/daily/YYYY-MM-DD/visual/requests.retried.json
```

事实错误退回编辑阶段；构图、主体、文字、风格和裁切问题才进入图片重试。

### 4. 多平台独立模板导出

```bash
python scripts/export_platform_assets.py \
  --visual-queue data/daily/YYYY-MM-DD/visual/queue.json \
  --requests data/daily/YYYY-MM-DD/visual/requests.reviewed.json \
  --review data/daily/YYYY-MM-DD/visual/review.json \
  --output-dir data/daily/YYYY-MM-DD/visual/platforms \
  --manifest data/daily/YYYY-MM-DD/visual/export-manifest.json

python scripts/validate_platform_exports.py \
  --manifest data/daily/YYYY-MM-DD/visual/export-manifest.json
```

正式输出：

- `vertical_9x16`：2160×3840
- `portrait_3x4`：2160×2880
- `landscape_16x9`：2560×1440
- `wechat_cover_235x1`：2350×1000

每个比例使用独立布局，不直接裁切 9:16 成品。

## 多平台内容包

### 1. 生成内容包

```bash
python scripts/build_content_packages.py \
  --run-dir data/daily/YYYY-MM-DD \
  --export-manifest data/daily/YYYY-MM-DD/visual/export-manifest.json \
  --output data/daily/YYYY-MM-DD/publishing/content-packages.json
```

### 2. 生成无写入发布计划

```bash
python scripts/build_publication_plan.py \
  --packages data/daily/YYYY-MM-DD/publishing/content-packages.json \
  --created-at 2026-07-29T16:30:00+08:00 \
  --output data/daily/YYYY-MM-DD/publishing/publication-plan.json
```

### 3. 明确人工确认

```bash
python scripts/approve_publication_plan.py \
  --plan data/daily/YYYY-MM-DD/publishing/publication-plan.json \
  --decisions data/daily/YYYY-MM-DD/publishing/decisions.json \
  --approval-output data/daily/YYYY-MM-DD/publishing/approval.json \
  --plan-output data/daily/YYYY-MM-DD/publishing/publication-plan.approved.json
```

批准只确认平台、文案哈希、图片哈希、图片顺序和风险检查；程序写入权限仍为关闭。

### 4. 生成本地预览

```bash
python scripts/preview_publication.py \
  --packages data/daily/YYYY-MM-DD/publishing/content-packages.json \
  --plan data/daily/YYYY-MM-DD/publishing/publication-plan.approved.json \
  --approval data/daily/YYYY-MM-DD/publishing/approval.json \
  --executed-at 2026-07-29T16:40:00+08:00 \
  --output-dir data/daily/YYYY-MM-DD/publishing/preview \
  --result data/daily/YYYY-MM-DD/publishing/result.json
```

结果固定为 `dry_run`，不会登录或写入任何平台。完整规范见 [`docs/PUBLISHING.md`](docs/PUBLISHING.md)。

## CI

当前包含：

- `Schema Validation`
- `Visual Generation Validation`
- `Multi-platform Export Validation`
- `Publication Package Validation`
- `HXP Daily Pipeline Plan`

CI 不调用付费图片 API，不访问真实发布平台。视觉和发布验证使用带测试标识的 Logo 与离线 Fixture。

## 首份端到端归档

`data/daily/2026-07-29/` 包含：

- 6 个已核对的一手来源
- 7 个候选事件
- 5 条正式入选
- 2 条内部淘汰
- 评分、简报、Markdown 与运行清单

该归档仍保持 `review_status=pending`，因此不能进入正式发布。

## 项目阶段

- Phase 1.1：核心数据 Schema ✅
- Phase 1.2：六 Agent Prompt Engine ✅
- Phase 1.3：示例、校验、CI 与自动化入口 ✅
- Phase 2.1：官方来源注册表与候选池 ✅
- Phase 2.2：RSS / HTML 采集与原始快照 ✅
- Phase 2.3：稳定指纹与 3 / 7 / 30 天去重 ✅
- Phase 3.1：编辑评分与日报组装器 ✅
- Phase 3.2：首份真实每日运行包 ✅
- Phase 3.3：调度、水位、历史提交与失败告警 ✅
- Phase 4.1：固定 SVG / PNG 海报、中文排版与视觉队列 ✅
- Phase 4.2：AI 主视觉、人工审核、定向重试与多平台导出 ✅
- Phase 5.1：多平台内容包、发布计划、人工确认与本地预览 ✅
- Phase 5.2：逐平台草稿连接器与最小权限写入 ⏳
