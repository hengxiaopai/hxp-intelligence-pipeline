# 多平台内容分发与 RED Skill 生态调研

> 调研日期：2026-07-29  
> 目标：为 HXP Intelligence Pipeline 选择可复用的多平台草稿连接器、浏览器桥接方案与 Skill 分发路径。  
> 本文只做架构与能力调研，不启用任何真实账号写入。

## 1. 结论先行

当前最适合珩小派的路线不是“重新实现所有平台发布逻辑”，而是采用三层连接器策略：

1. **官方 API 直连层**：网站、Halo、WordPress、Ghost、具备权限的微信公众号等。
2. **本地浏览器桥接层**：知乎、小红书、抖音、头条、掘金、CSDN 等缺少稳定公共发布 API 的平台。
3. **人工交接层**：高风险、强验证、验证码或平台规则变化频繁的平台。

首个优先研究和适配对象应是 **Wechatsync 本地桥接连接器**。它已经覆盖 29+ 平台，支持 CLI、MCP、浏览器扩展、草稿优先和本地登录态，可显著减少重复开发。

小红书官方 **RED Skill** 应被视为“Skill 分发渠道”，而不是“小红书笔记发布 API”。HXP 可单独制作一个 `hxp-intelligence-publisher` 或 `hxp-content-repurposing` Skill，上传 RED Skill 并挂载到小红书笔记，用于品牌传播和用户安装；实际笔记发布仍走浏览器桥接或人工确认。

---

## 2. 核心候选项目

### 2.1 Wechatsync / 文章同步助手

- 仓库：https://github.com/wechatsync/Wechatsync
- 类型：Chrome 扩展 + CLI + MCP Server + JS SDK
- 支持：微信公众号、知乎、微博、小红书、抖音图文、头条、掘金、CSDN、B 站专栏、WordPress、Typecho、X 等 29+ 平台
- 登录方式：复用用户浏览器现有登录态
- 发布方式：调用各平台 Web 编辑器使用的接口
- 默认行为：保存草稿，人工确认后再发布
- AI 接入：Anthropic MCP、Claude Code Skill、OpenClaw、CLI

#### 可复用设计

- `packages/core` 与各入口分离：扩展、MCP、CLI 共享核心逻辑。
- 平台适配器统一注册，便于快速增加新平台。
- 浏览器登录态保留在本地，中央流水线不接触账号密码。
- CLI 命令支持一次指定多个平台。
- 有 `list_platforms`、`check_auth`、`sync_article`、`extract_article`、图片上传等标准能力。

#### 对 HXP 的价值

可作为 Phase 5.2B 的首选“聚合连接器”。HXP 只需要把已经审核通过的内容包和图片顺序交给本地 Wechatsync Bridge，不必为知乎、掘金、CSDN、头条等逐一重写适配器。

#### 风险

- 浏览器 Cookie 和平台 Web 接口具有时效性。
- 平台前端或接口变化后可能需要更新适配器。
- 小红书、抖音等平台仍可能触发验证码或风控。
- HXP 必须继续保持逐次人工授权、草稿优先和幂等账本。

---

### 2.2 MultiPost

- 仓库：https://github.com/leaperone/MultiPost-Extension
- 类型：浏览器扩展 + Extension API + RESTful API
- 支持：知乎、微博、小红书、抖音、TikTok、YouTube 等 10+ 平台
- 特点：无需额外注册、无需 API Key，依赖用户已经登录的平台会话
- 配套：在线 Markdown 编辑器与开发者 API

#### 可复用设计

- 将浏览器扩展暴露成应用可调用的本地发布能力。
- 同时提供扩展 API 和 REST API，适合桌面端、网页端、脚本和 Agent。
- 内容、图片、视频统一抽象为发布任务。

#### 对 HXP 的价值

是 Wechatsync 的重要备选。适合设计一个通用 `local_browser_bridge` 协议，使 HXP 可以在不修改核心流水线的情况下切换 Wechatsync 或 MultiPost。

#### 风险

- 仍依赖浏览器会话和平台页面稳定性。
- 需要验证其草稿模式、错误回传和平台级幂等能力是否满足 HXP 的严格要求。

---

### 2.3 jiji262/wechat-publisher

- 仓库：https://github.com/jiji262/wechat-publisher
- 类型：微信公众号创作、排版、图片上传和草稿发布 Skill
- 功能：Markdown 转微信 HTML、图片 CDN、封面、摘要、草稿创建、AI 味检查
- 多平台：可通过 `@wechatsync/cli` 将文章继续同步到知乎、掘金等平台

#### 可复用设计

- 把内容创作、视觉生成、排版、质量门槛和草稿创建拆成阶段。
- 发布前设置内容质量 Gate。
- 微信公众号作为源内容，再通过 Wechatsync 扩散。

#### 对 HXP 的价值

适合参考其微信公众号 HTML 转换、图片 CDN、草稿创建和内容质量门槛，但 HXP 应继续保留自己的事实审核、品牌模板和人工授权体系。

---

### 2.4 xpzouying/xiaohongshu-mcp

- 仓库：https://github.com/xpzouying/xiaohongshu-mcp
- 类型：本地 MCP Server + 浏览器登录
- 功能：登录、图文发布、视频发布、定时发布、搜索、详情、评论等
- 输入：标题、正文、本地图片路径或 URL、标签、可见范围、定时时间

#### 可复用设计

- 用 MCP 暴露平台能力。
- 登录状态和 Cookie 保存在本地运行环境。
- 图片和视频采用本地绝对路径，减少远程链接失效。
- 将发布、搜索和互动拆成独立工具。

#### 对 HXP 的价值

适合用于“小红书专用本地连接器”的技术验证，也可作为 Wechatsync 不满足小红书特殊字段时的备用路径。

#### 风险

- 属于社区项目，不是小红书官方发布 API。
- 自动公开发布风险高，可能触发平台风控。
- HXP 不应默认启用互动、评论或批量操作。
- 正式接入时必须把“到发布页停手 / 保存草稿 / 最终点击确认”做成独立授权步骤。

---

### 2.5 autoclaw-cc/xiaohongshu-skills

- 仓库：https://github.com/autoclaw-cc/xiaohongshu-skills
- 类型：浏览器自动化 + 多个 SKILL.md 子技能
- 子技能：认证、发布、探索、互动、内容运营
- 支持：图文、视频、长文发布，以及内容搜索和互动

#### 可复用设计

- 一个总入口 Skill 路由到多个职责单一的子 Skill。
- 浏览器桥接、本地 Cookie、媒体下载缓存、UTF-16 标题长度、单实例锁等工程细节较完整。
- 将发布、搜索、互动、内容运营拆分，避免单个 Skill 权限过大。

#### 对 HXP 的价值

适合参考 HXP Skill 的目录设计：

```text
skills/
├── hxp-auth/
├── hxp-publish-draft/
├── hxp-content-adapt/
├── hxp-review/
└── hxp-status/
```

不建议直接复制其自动互动和高频运营逻辑。

---

### 2.6 jackwener/xhs-cli 与 xiaohongshu-cli

- 仓库：https://github.com/jackwener/xhs-cli
- 仓库：https://github.com/jackwener/xiaohongshu-cli
- 类型：CLI + SKILL.md
- 两种路线：
  - `xhs-cli`：无头浏览器，速度较慢，但更接近真实用户流程。
  - `xiaohongshu-cli`：逆向接口，速度更快，但平台稳定性和合规风险更高。

#### 对 HXP 的价值

可参考统一 JSON/YAML 输出、CLI 作为 Agent Skill、能力发现和错误封装。正式发布优先考虑浏览器路线，不采用逆向接口作为默认生产依赖。

---

### 2.7 jackwener/OpenCLI

- 仓库：https://github.com/jackwener/OpenCLI
- 类型：统一 CLI + Browser Bridge
- 方向：为小红书、即刻、微信等平台提供命令式访问和发布能力
- 微信公众号实践显示：草稿创建可以自动化，但最终发表可能仍需扫码确认。

#### 对 HXP 的价值

可参考统一命令空间、Browser Bridge、账号状态检查和“草稿自动化、最终发表人工确认”的边界。

---

### 2.8 Artipub

- 仓库：https://github.com/artipub/artipub
- 文档：https://artipub.github.io/artipub/
- 类型：Markdown 多平台发布库
- 架构：Publisher Plugin + Middleware
- 内置方向：Notion、Dev.to、本地输出、图片压缩、图片上传

#### 可复用设计

- 发布器插件只负责平台转换和 API 调用。
- 中间件负责图片压缩、上传和内容转换。
- 核心不感知具体平台。

#### 对 HXP 的价值

适合强化当前 `publishing/connectors` 架构：

```text
content package
  → middleware chain
  → platform adapter
  → connector gate
  → draft result
```

---

### 2.9 AiToEarn / TurboPush 等桌面矩阵工具

- 仓库：https://github.com/yikart/AiToEarn
- 参考：https://github.com/xueyc1f/turbopush-website
- 类型：Electron / Tauri 桌面应用，多账号、多平台、图文和视频发布

#### 对 HXP 的价值

适合研究桌面客户端如何管理浏览器实例、账号矩阵、任务队列和发布状态，但不建议把其账号管理或自动公开发布逻辑直接并入 HXP 核心。

---

## 3. 小红书官方 RED Skill

### 3.1 它是什么

RED Skill 是小红书在 2026 年上线的 Skill 分发功能。创作者可在创作服务平台上传 Skill 文件，审核后挂载到笔记；用户点击组件后复制安装口令，再交给 Claude Code、Codex、OpenClaw 等 Agent 安装。

目前 RED Skill 的核心价值是：

- Skill 发现与分发；
- 笔记挂载和传播；
- Skill 使用人数和生态曝光；
- 把 GitHub / SKILL.md 的技术内容转化为普通用户可发现的产品。

### 3.2 它不是什么

RED Skill **不是**小红书图文笔记发布 API，也不直接替代：

- 小红书登录；
- 图文或视频上传；
- 草稿箱管理；
- 最终公开发布确认；
- 发布状态回查。

因此应把它建模为新的分发平台：

```text
platform = red_skill
content_type = skill_package
operation = upload_skill / attach_skill / update_skill / unlist_skill
```

而不是：

```text
platform = xiaohongshu
operation = publish_note
```

### 3.3 HXP 的机会

建议制作两个正式 Skill：

#### HXP Intelligence Skill

- 读取结构化 briefing；
- 输出微信公众号、小红书、抖音、知乎和 X 内容包；
- 强制来源、风险和人工确认；
- 默认不执行真实发布。

#### HXP Visual Brief Skill

- 把一条事实拆为无文字主视觉 Brief；
- 输出 9:16、3:4、16:9、2.35:1 构图要求；
- 检查中文、Logo、数据和事实边界；
- 生成可交给 ChatGPT Image 的任务包。

这两个 Skill 可通过 GitHub、Skills CLI 和小红书 RED Skill 同时分发。

---

## 4. 推荐技术架构

### 4.1 连接器模式

在 `connector-capability.schema.json` 中建议扩展：

```json
{
  "mode": "official_api | local_browser_bridge | local_mcp | manual_handoff | simulator",
  "session_location": "local_only | server_secret_store | none",
  "final_confirmation": "required | optional | unsupported",
  "draft_supported": true,
  "public_publish_supported": false,
  "risk_level": "low | medium | high"
}
```

### 4.2 统一本地桥接协议

不让 HXP 核心直接依赖某个扩展，定义统一请求：

```json
{
  "connector": "wechatsync-local",
  "platform": "zhihu",
  "action": "draft_only",
  "account_ref": "local-browser-profile-1",
  "content_hash": "...",
  "ordered_assets": ["..."],
  "idempotency_key": "...",
  "requires_final_confirmation": true
}
```

本地适配器可分别实现：

- Wechatsync CLI / MCP；
- MultiPost REST / Extension API；
- Xiaohongshu MCP；
- OpenCLI Browser Bridge；
- 人工交接包。

### 4.3 权限边界

- 核心服务不保存 Cookie、密码、二维码、浏览器 Profile 或平台私密响应。
- 本地桥接只接收已经人工批准的内容哈希和有序图片哈希。
- 所有平台默认 `draft_only`。
- 自动公开发布保持关闭。
- 验证码、扫码、风控、身份不符、页面漂移时立即停止。
- 每次写入使用一次性授权和幂等键。
- 同一幂等键但内容或图片变化必须硬阻断。

---

## 5. 推荐实施顺序

### Phase R1：适配 Wechatsync 本地桥接

目标平台：

1. 知乎
2. 掘金
3. CSDN
4. 头条号
5. WordPress / Typecho
6. 小红书和抖音只做实验性草稿或人工交接

交付：

- `wechatsync-local` 能力注册；
- 本地 CLI / MCP 探测；
- 登录状态检查；
- 草稿同步请求；
- 错误分类和平台状态回传；
- 仍保持最终发布人工确认。

### Phase R2：小红书专用连接器实验

对比：

- Wechatsync 小红书适配器；
- MultiPost 小红书适配器；
- xpzouying/xiaohongshu-mcp；
- xhs-cli 浏览器路线。

评估项：

- 是否能保存草稿而不是直接公开；
- 图片顺序；
- 标题 UTF-16 长度；
- 标签选择；
- 可见范围；
- 原创声明；
- 验证码与风控停止；
- 发布后状态回查；
- 页面变化后的修复成本。

### Phase R3：知乎内容包与浏览器桥接

补齐 HXP 当前缺失的知乎专属内容包：

- 回答 / 文章两种模型；
- 标题、导语、正文、引用来源；
- Markdown / HTML 转换；
- 封面和正文图片；
- 文章草稿保存；
- 不自动点击最终发布。

### Phase R4：RED Skill 分发

- 打包 `hxp-intelligence-publisher/SKILL.md`；
- 加入安装、权限、输入输出和安全说明；
- GitHub Release；
- RED Skill 上传材料；
- 小红书介绍笔记与挂载组件；
- 使用人数、反馈和版本回收。

---

## 6. 采用建议

| 项目 / 生态 | 建议 | 用途 |
|---|---|---|
| Wechatsync | 优先适配 | 多平台本地草稿桥接 |
| MultiPost | 作为第二实现 | 通用浏览器扩展 API / REST Bridge |
| wechat-publisher | 局部参考 | 微信排版、CDN、草稿和内容 Gate |
| xiaohongshu-mcp | 实验性评估 | 小红书专用 MCP 连接器 |
| xiaohongshu-skills | 参考 Skill 结构 | 子技能拆分、浏览器流程和运营知识库 |
| xhs-cli | 参考浏览器 CLI | 结构化输出和本地会话 |
| xiaohongshu-cli 逆向接口 | 不作为默认生产依赖 | 仅研究，不进入正式发布路径 |
| OpenCLI | 参考统一命令和 Browser Bridge | 草稿自动化 + 最终扫码确认 |
| Artipub | 参考插件架构 | 中间件和 Publisher Plugin |
| RED Skill | 建立独立分发渠道 | 发布和传播 HXP Skills |

---

## 7. 参考来源

- https://github.com/wechatsync/Wechatsync
- https://github.com/leaperone/MultiPost-Extension
- https://github.com/jiji262/wechat-publisher
- https://github.com/xpzouying/xiaohongshu-mcp
- https://github.com/autoclaw-cc/xiaohongshu-skills
- https://github.com/jackwener/xhs-cli
- https://github.com/jackwener/xiaohongshu-cli
- https://github.com/jackwener/OpenCLI
- https://github.com/artipub/artipub
- https://github.com/yikart/AiToEarn
- https://github.com/xueyc1f/turbopush-website
- https://redskill.xiaohongshu.net/install.md
