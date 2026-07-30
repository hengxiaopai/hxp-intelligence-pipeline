# HXP Intelligence Pipeline

珩小派多元情报采集、审核、海报生成、内容适配与安全发布准备流水线。

## 项目目标

将每日情报生产拆成可追溯、可重放且默认不自动发布的流程：

1. **计划与采集**：按来源优先级、最小间隔和最大时效生成采集计划。
2. **审核与组装**：事实核验、3 / 7 / 30 天去重、编辑评分和日报组装。
3. **人工批准**：自动校验通过后仍保持待审核，批准后才能推进历史、视觉和发布准备。
4. **视觉与归档**：AI 生成无文字主视觉，固定模板排版中文并导出多平台资产。
5. **内容适配**：为微信公众号、小红书、抖音图文、X 和网站生成独立草稿内容包。
6. **无扩展发布驾驶舱**：集中复制文案、下载有序图片、打开官方创作入口，并由用户手动记录结果。
7. **连接器安全层**：官方连接器仍需绑定平台、账号、文案哈希、图片哈希、顺序、动作和有效期。

## 核心原则

- 不为凑数引入低价值信息；每日合格焦点目标为 5–8 条。
- 连续热点只记录可证实的新增变化。
- 政策、金融、财务、安全等内容优先使用官方或一手来源。
- 评分、排序、入选、淘汰、历史提交和视觉资产必须可解释、可重放。
- **AI 生视觉，模板排文字**，不依赖图片模型渲染大段中文。
- 仓库不保存或分发字体文件；正式 Logo 必须使用主理人批准的品牌资产。
- 实时采集、平台凭据、真实草稿写入和公开发布全部默认关闭。
- 不绕过验证码、风控、平台协议、登录限制或人工确认。
- 浏览器扩展和本地桥接只作为可选增强，不是主流程前置条件。

## 快速验证

```bash
python -m pip install -r requirements-dev.txt
python scripts/validate.py --examples
python scripts/source_registry.py --validate
python scripts/validate_candidate.py
python scripts/validate_daily_run.py --run-dir data/daily/2026-07-29
python scripts/inspect_connector_capabilities.py
python -m unittest discover -s tests -v
```

Linux PNG 导出还需要：

```bash
sudo apt-get install -y libcairo2 libpango-1.0-0 fonts-noto-cjk
```

## 每日情报流程

```text
来源计划
  ↓
RSS / HTML 安全采集
  ↓
候选规范化
  ↓
3 / 7 / 30 天去重
  ↓
编辑评分与日报组装
  ↓
人工事实审核
  ↓
历史提交
```

完整命令见 [`docs/RUNBOOK.md`](docs/RUNBOOK.md)。

## 视觉流程

```text
approved briefing
  ↓
固定视觉队列
  ↓
无文字主视觉请求
  ↓
ChatGPT 图片生成 / 离线 Fixture
  ↓
SHA-256 结果导入
  ↓
人工视觉审核
  ↓
定向重试
  ↓
9:16 / 3:4 / 16:9 / 2.35:1 独立模板
```

主要入口：

```bash
python scripts/build_visual_queue.py --help
python scripts/build_visual_requests.py --help
python scripts/import_visual_results.py --help
python scripts/review_visuals.py --help
python scripts/retry_failed_visuals.py --help
python scripts/export_platform_assets.py --help
python scripts/validate_platform_exports.py --help
```

正式 Logo、每条主视觉、批准状态和无占位符检查缺一不可。完整规范见：

- [`docs/VISUAL-PIPELINE.md`](docs/VISUAL-PIPELINE.md)
- [`docs/AI-VISUALS.md`](docs/AI-VISUALS.md)
- [`docs/MULTI-PLATFORM-EXPORT.md`](docs/MULTI-PLATFORM-EXPORT.md)

## 多平台内容包

```text
briefing.json + export-manifest.json
  ↓
微信公众号内容包
小红书图文内容包
抖音图文内容包
X 内容包
网站文章草稿
  ↓
无写入发布计划
  ↓
人工确认平台 / 文案 / 图片 / 顺序
  ↓
本地 HTML + Markdown 预览
```

主要入口：

```bash
python scripts/build_content_packages.py --help
python scripts/build_publication_plan.py --help
python scripts/approve_publication_plan.py --help
python scripts/preview_publication.py --help
```

Phase 5.1 结果始终保持：

```json
{
  "write_actions_enabled": false,
  "write_allowed": false,
  "execution_mode": "dry_run",
  "external_write_performed": false
}
```

完整规范见 [`docs/PUBLISHING.md`](docs/PUBLISHING.md)。

## 无扩展发布驾驶舱

驾驶舱不安装浏览器扩展，不读取 Cookie，不使用 Playwright、CDP 或 DOM 注入。它把现有五个平台内容包扩展为六个平台交接目录，并从网站长文确定性派生知乎文章版和回答版。

```text
validated content packages
  ↓
六平台交接目录
  ├── 微信公众号
  ├── 小红书
  ├── 抖音图文
  ├── X
  ├── 珩小派网站
  └── 知乎文章版 / 回答版
  ↓
单文件离线 cockpit.html
  ├── 用户点击后复制标题、正文、话题和线程
  ├── 查看图片顺序、尺寸和 SHA-256
  ├── 下载 JSON / Markdown / 纯文本
  ├── 打开白名单 HTTPS 官方创作入口
  └── 人工记录已打开、已粘贴、已存草稿或已发布
```

构建交接包：

```bash
python scripts/build_handoff_bundle.py \
  --packages /path/to/content-packages.json \
  --output-dir /path/to/handoff \
  --manifest /path/to/handoff/manifest.json \
  --generated-at 2026-07-30T13:00:00+08:00
```

生成离线驾驶舱：

```bash
python scripts/build_publishing_cockpit.py \
  --manifest /path/to/handoff/manifest.json \
  --output /path/to/handoff/cockpit.html
```

初始化人工状态记录：

```bash
python scripts/record_manual_publication.py \
  --manifest /path/to/handoff/manifest.json \
  --updated-at 2026-07-30T13:10:00+08:00 \
  --session-slug owner \
  --output /path/to/handoff/session.json
```

程序不会根据打开页面、复制内容或进程退出码推断发布成功。任何已发布状态必须由用户明确确认，并填写平台内容 ID 或 HTTPS 链接；内容或图片哈希发生变化后，旧状态不能复用。

完整规范见 [`docs/PUBLISHING-COCKPIT.md`](docs/PUBLISHING-COCKPIT.md)。

## 连接器授权与 Simulator

当前仅启用：

```text
simulator-draft
platform=website
mode=simulator
action=draft_only
```

真实网站、微信公众号和其他平台连接器均已登记或规划，但保持关闭。

```bash
python scripts/inspect_connector_capabilities.py

python scripts/issue_connector_authorization.py \
  --plan publication-plan.approved.json \
  --connector-id simulator-draft \
  --entry-id publication-entry-YYYYMMDD-website \
  --account-ref hxp-website-staging \
  --issued-at 2026-07-29T16:00:00+08:00 \
  --expires-at 2026-07-29T17:00:00+08:00 \
  --issued-by hengxiaopai \
  --output connector-authorization.json

python scripts/build_connector_request.py \
  --authorization connector-authorization.json \
  --plan publication-plan.approved.json \
  --package-id content-package-YYYYMMDD-website \
  --account-ref hxp-website-staging \
  --requested-at 2026-07-29T16:30:00+08:00 \
  --request-output connector-request.json \
  --authorization-output connector-authorization.consumed.json

python scripts/simulate_connector_write.py \
  --request connector-request.json \
  --executed-at 2026-07-29T16:31:00+08:00 \
  --result-output connector-result.json \
  --ledger-output connector-ledger.json
```

授权是一次性的，并绑定平台、账号、发布条目、文案 SHA-256、按顺序排列的图片 SHA-256、动作和到期时间。任意漂移、过期、撤销或复用都会硬阻断。相同幂等键的完全一致请求只返回既有模拟结果。

完整规范见 [`docs/CONNECTORS.md`](docs/CONNECTORS.md)。

## CI

当前包含：

- `Schema Validation`
- `Visual Generation Validation`
- `Multi-platform Export Validation`
- `Publication Package Validation`
- `Publishing Cockpit Validation`
- `Connector Gate Validation`
- `Local Browser Bridge Validation`
- `HXP Daily Pipeline Plan`

CI 不调用付费图片 API，不访问真实发布平台，不读取真实平台凭据。视觉与发布验证均使用明确标记的离线 Fixture。

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
- Phase 5.1：五平台内容包、发布计划与无写入人工确认 ✅
- Phase 5.2A：连接器能力、一次性授权、幂等账本与离线 Simulator ✅
- Phase 5.3A：本地浏览器桥接协议与离线验证，可选增强 ✅
- Phase 5.3B：无扩展发布驾驶舱与知乎人工交接包 🚧
- Phase 5.4：网站 / Halo、微信公众号、抖音、小红书官方能力连接器 ⏳
