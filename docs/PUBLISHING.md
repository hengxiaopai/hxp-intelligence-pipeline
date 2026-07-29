# 多平台内容包与发布确认

## 范围

Phase 5.1 只生成可审计的草稿内容包、发布计划、人工确认记录和本地预览。

本阶段明确禁止：

- 登录微信公众号、小红书、抖音、X 或网站后台；
- 保存账号密码、Cookie、Authorization、Token 或私密平台响应；
- 调用真实发布接口；
- 自动接受平台协议、验证码或风控挑战；
- 将 `approved` 误解为允许程序写入平台。

即使人工审核通过，计划仍保持：

```json
{
  "write_actions_enabled": false,
  "write_allowed": false,
  "execution_mode": "dry_run",
  "external_write_performed": false
}
```

## 输入

- 已批准的 `briefing.json`；
- 已通过质检的 `export-manifest.json`；
- 完整来源 JSON；
- `config/platform-profiles.json`。

平台与视觉预设：

| 平台 | 预设 | 内容形态 |
|---|---|---|
| 微信公众号 | `wechat_cover_235x1` | 标题、120 字内摘要、完整 Markdown 正文、来源 |
| 小红书 | `portrait_3x4` | 封面标题、图文说明、话题与 6 图顺序 |
| 抖音图文 | `vertical_9x16` | 标题、描述、话题与 6 图顺序 |
| X | `landscape_16x9` | 单帖、可选线程、来源与 1 张总览图 |
| 珩小派网站 | `landscape_16x9` | 文章草稿、SEO、slug、总览与详情图 |

## 1. 生成五个平台内容包

```bash
python scripts/build_content_packages.py \
  --run-dir data/daily/YYYY-MM-DD \
  --export-manifest data/daily/YYYY-MM-DD/visual/export-manifest.json \
  --output data/daily/YYYY-MM-DD/publishing/content-packages.json
```

生成器会检查：

- Export Manifest 日期、状态、尺寸记录和图片哈希；
- 每个平台是否使用正确预设；
- 来源简称是否完整；
- 内部淘汰池是否未进入公开内容；
- 是否包含账号凭据、Cookie、Token 或私密 URL；
- 金融或 A 股内容是否包含“不构成投资建议”；
- 标题、正文、话题和线程是否符合平台长度上限。

相同输入会生成相同的 `content_hash`。

## 2. 生成发布计划

```bash
python scripts/build_publication_plan.py \
  --packages data/daily/YYYY-MM-DD/publishing/content-packages.json \
  --created-at 2026-07-29T16:30:00+08:00 \
  --output data/daily/YYYY-MM-DD/publishing/publication-plan.json
```

每个平台记录：

- 内容包 ID；
- 内容哈希；
- 图片哈希及顺序；
- 稳定幂等键；
- 风险标记；
- 账号占位符；
- `draft_only` 动作；
- `pending`、`approved`、`rejected` 或 `blocked` 状态。

Phase 5.1 的 `write_allowed` 永远为 `false`。

## 3. 人工确认

确认文件必须逐个平台核对：

- 平台；
- 目标账号占位符；
- 文案哈希；
- 图片哈希；
- 图片顺序；
- 风险提示；
- 计划动作。

```bash
python scripts/approve_publication_plan.py \
  --plan data/daily/YYYY-MM-DD/publishing/publication-plan.json \
  --decisions data/daily/YYYY-MM-DD/publishing/decisions.json \
  --approval-output data/daily/YYYY-MM-DD/publishing/approval.json \
  --plan-output data/daily/YYYY-MM-DD/publishing/publication-plan.approved.json
```

审核通过只代表内容版本已确认，不代表连接器获得平台写入权限。

## 4. 本地预览

```bash
python scripts/preview_publication.py \
  --packages data/daily/YYYY-MM-DD/publishing/content-packages.json \
  --plan data/daily/YYYY-MM-DD/publishing/publication-plan.approved.json \
  --approval data/daily/YYYY-MM-DD/publishing/approval.json \
  --executed-at 2026-07-29T16:40:00+08:00 \
  --output-dir data/daily/YYYY-MM-DD/publishing/preview \
  --result data/daily/YYYY-MM-DD/publishing/result.json
```

每个平台生成：

- 一个 Markdown 草稿；
- 一个本地 HTML 预览；
- 按确认顺序复制的图片；
- 一条 `dry_run` 结果记录。

HTML 预览不加载外部脚本，也不会向任何平台发送请求。

## 5. 失败处理

- 来源缺失：退回情报与编辑阶段；
- 图片未通过：退回视觉审核阶段；
- 文案超限：只修改对应平台内容包；
- 图片顺序或哈希变化：旧批准自动失效，重新人工确认；
- A 股风险说明缺失：阻断该平台内容包；
- 发现凭据或私密数据：阻断整个包，不做自动清洗后继续发布；
- 幂等键重复：不得生成第二次写入动作。

## 6. CI

`Publication Package Validation` 全程离线完成：

1. 生成测试主视觉；
2. 生成并验证 24 张多比例资产；
3. 生成 5 个平台内容包；
4. 生成发布计划；
5. 应用人工确认 Fixture；
6. 生成 5 份 HTML 和 5 份 Markdown 预览；
7. 断言 `external_write_performed=false`；
8. 上传 `hxp-publication-preview-2026-07-29` Artifact。

测试 Logo、测试图片和 Fixture 不得公开发布。

## 下一阶段

Phase 5.2 才评估逐平台草稿连接器。每个平台需要独立授权、独立确认、最小权限、幂等写入和失败停止策略；默认仍不自动发布。
