# 无扩展多平台发布驾驶舱

## 定位

发布驾驶舱把已经通过事实、视觉和平台规则审核的内容包，转换为六个平台的本地交接目录和一个离线 HTML 页面。

它不依赖 Chrome 扩展，不读取浏览器 Cookie，不调用 Playwright / CDP，不自动填写网页，也不执行真实平台写入。

```text
内容包
  ↓
六平台交接目录
  ↓
离线发布驾驶舱
  ├── 复制标题 / 摘要 / 正文 / 话题 / 线程
  ├── 查看图片顺序、尺寸和 SHA-256
  ├── 下载 Markdown / 纯文本 / JSON
  ├── 打开白名单官方创作入口
  └── 人工记录已打开 / 已粘贴 / 已存草稿 / 已发布
```

## 平台范围

- 微信公众号
- 小红书
- 抖音图文
- X
- 珩小派网站
- 知乎

前五个平台直接使用 Phase 5.1 已验证内容包。知乎在交接阶段从网站长文内容确定性派生两个版本：

1. **文章版**：标题、摘要、完整 Markdown、图片顺序、来源和风险声明；
2. **回答版**：问题占位提示、开头结论、分段正文、来源、AI 辅助说明和风险声明。

问题占位文字不能直接作为知乎问题发布。用户必须先选择一个真实、相关且仍有讨论价值的问题。

## 构建交接包

```bash
python scripts/build_handoff_bundle.py \
  --packages /path/to/content-packages.json \
  --output-dir /path/to/handoff \
  --manifest /path/to/handoff/manifest.json \
  --generated-at 2026-07-30T13:00:00+08:00
```

输出：

```text
handoff/
├── manifest.json
├── wechat/
│   ├── content.json
│   ├── content.md
│   ├── content.txt
│   └── assets/
├── xiaohongshu/
├── douyin/
├── x/
├── website/
└── zhihu/
```

每张图片在复制前都会重新计算 SHA-256。任何图片缺失、内容哈希不一致、平台内容未通过验证或入口 URL 不符合白名单，都会硬阻断。

## 生成离线驾驶舱

```bash
python scripts/build_publishing_cockpit.py \
  --manifest /path/to/handoff/manifest.json \
  --output /path/to/handoff/cockpit.html
```

双击 `cockpit.html` 即可本地使用。页面包含：

- 六个平台卡片；
- 标题、摘要、正文、话题、线程、SEO 和来源；
- 用户点击后才执行的一键复制；
- 图片顺序、尺寸与哈希；
- Markdown、纯文本和 JSON 下载；
- HTTPS 官方创作入口；
- 发布前人工检查清单。

页面不加载任何外部 JavaScript 或 CSS，也不会读取剪贴板历史。复制仅在用户点击按钮后写入剪贴板。

## 人工状态记录

初始化：

```bash
python scripts/record_manual_publication.py \
  --manifest /path/to/handoff/manifest.json \
  --updated-at 2026-07-30T13:10:00+08:00 \
  --session-slug owner \
  --output /path/to/handoff/session.json
```

记录已打开平台页面：

```bash
python scripts/record_manual_publication.py \
  --manifest /path/to/handoff/manifest.json \
  --session /path/to/handoff/session.json \
  --platform zhihu \
  --status opened \
  --confirmed-by-user \
  --updated-at 2026-07-30T13:12:00+08:00 \
  --output /path/to/handoff/session.next.json
```

记录已发布必须由用户提供平台内容 ID 或 HTTPS URL：

```bash
python scripts/record_manual_publication.py \
  --manifest /path/to/handoff/manifest.json \
  --session /path/to/handoff/session.json \
  --platform website \
  --status published \
  --confirmed-by-user \
  --external-url https://hengxiaopai.com/articles/example \
  --updated-at 2026-07-30T14:00:00+08:00 \
  --output /path/to/handoff/session.next.json
```

状态：

- `not_started`
- `opened`
- `pasted`
- `draft_saved`
- `published`
- `failed`
- `skipped`

程序不会根据“打开页面”“复制内容”或命令退出码推断发布成功。内容哈希或图片哈希发生变化后，旧状态不能复用。

## 官方入口白名单

配置位于 `config/cockpit-platforms.json`。

入口必须：

- 使用 HTTPS；
- 域名与白名单完全匹配；
- 不包含账号、密码、Token、查询参数或 URL 片段；
- 只负责打开创作入口，不代表登录、草稿或发布成功。

## 安全边界

始终保持：

```json
{
  "extensions_required": false,
  "external_write_enabled": false,
  "browser_automation_enabled": false,
  "external_write_performed": false
}
```

禁止：

- 保存 Cookie、密码、二维码或浏览器 Profile；
- Playwright、CDP、DOM 注入和无感自动填写；
- 绕过验证码、审核、登录或平台规则；
- 将打开页面误记为发布成功；
- 使用旧内容哈希确认新版本内容。

## 后续连接器

发布驾驶舱是长期保留的人工兜底层。官方连接器后续按风险从低到高独立实现：

1. 珩小派网站 / Halo 草稿；
2. 微信公众号官方草稿箱；
3. 抖音官方 Open API；
4. 小红书官方分享能力；
5. 浏览器桥接只作为可选增强，不再是前置依赖。
