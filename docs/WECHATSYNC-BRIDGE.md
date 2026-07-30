# Wechatsync 本地浏览器桥接

## 当前阶段

Phase 5.3A 只建立协议、Fixture、结果清洗和离线测试，不启动 Wechatsync、Chrome 或任何真实平台连接器。

固定状态：

```json
{
  "real_bridge_calls_enabled": false,
  "loopback_only": true,
  "remote_bridge_allowed": false,
  "execution_enabled": false,
  "public_publish_supported": false
}
```

## 为什么优先研究 Wechatsync

Wechatsync 已提供：

- Chrome 扩展；
- CLI；
- MCP Server；
- 多平台适配器；
- `list_platforms`、`check_auth`、`sync_article` 等结构化能力；
- 草稿优先的发布语义。

HXP 不复制二十多个平台的浏览器适配逻辑，而是在外层提供统一的内容哈希、图片哈希、人工批准、幂等、错误分类和审计协议。

## 上游风险与 HXP 修正

### 1. 远程监听

上游文档允许服务监听 `0.0.0.0:9527`，并支持远程浏览器连接。Token 在部分远程配置中可能以明文传输。

HXP 默认：

- 仅允许 `127.0.0.1`、`localhost` 或 `::1`；
- 禁止远程桥接；
- 禁止在服务器、防火墙或公网开放 9527 / 9528；
- 后续只读握手也必须由用户在本机显式授权。

### 2. CLI 退出码

Wechatsync CLI 面向人类交互，输出为彩色文本。平台级失败不应仅通过进程退出码判断。

HXP 规则：

- 优先使用 MCP / Bridge 的结构化 `results`；
- `cli_exit_code_authoritative=false`；
- CLI 在当前阶段只允许生成带 `--dry-run` 的命令预览；
- 未返回目标平台结果时，按失败处理。

### 3. 浏览器登录态

Cookie、密码、二维码和浏览器 Profile 只存在于用户本机浏览器，不进入 HXP 仓库、日志、Issue、Manifest 或 Artifact。

HXP 只允许记录：

- 环境变量是否存在；
- 扩展是否连接；
- 平台是否已登录；
- 脱敏后的账号引用；
- 草稿 ID 和经过清洗的 URL。

## 协议结构

```text
HXP approved content
        ↓
Browser Bridge Request
        ↓
Wechatsync MCP / CLI adapter
        ↓
Structured upstream response
        ↓
URL and error sanitization
        ↓
Browser Bridge Result
```

### 请求绑定

请求指纹绑定：

- bridge ID；
- provider；
- 操作；
- 目标平台；
- 账号引用；
- 文章 ID；
- 标题；
- Markdown 路径；
-正文 SHA-256；
- 图片 SHA-256；
- 封面路径；
- 来源简称。

`created_at` 不参与请求指纹，因此相同内容和目标平台会产生相同幂等标识。

### 第一批平台

Phase 5.3A 只建模：

- 知乎 `zhihu`
- 掘金 `juejin`
- CSDN `csdn`

小红书、抖音在后续浏览器专项评估中接入，仍默认停留在草稿或发布页，公开发布需要新的逐次确认。

## 命令

### 验证注册表

```bash
python scripts/inspect_local_bridges.py
```

### 构建离线草稿请求

```bash
python scripts/build_wechatsync_bridge_request.py \
  --operation create_draft \
  --platforms zhihu,juejin,csdn \
  --created-at 2026-07-30T09:00:00+08:00 \
  --article tests/fixtures/bridge/article.json \
  --account-ref hxp-browser-fixture \
  --transport fixture \
  --output /tmp/hxp-bridge/request.json
```

该命令不会执行桥接，输出固定包含：

```json
{
  "execution_allowed": false,
  "external_write_expected": false
}
```

### 解析登录状态 Fixture

```bash
python scripts/normalize_wechatsync_fixture.py \
  --kind health \
  --raw tests/fixtures/bridge/wechatsync-platforms.json \
  --at 2026-07-30T09:01:00+08:00 \
  --extension-connected true \
  --credential-present true \
  --output /tmp/hxp-bridge/health.json
```

### 解析草稿结果 Fixture

```bash
python scripts/normalize_wechatsync_fixture.py \
  --kind result \
  --request /tmp/hxp-bridge/request.json \
  --raw tests/fixtures/bridge/wechatsync-sync-result.json \
  --at 2026-07-30T09:02:00+08:00 \
  --output /tmp/hxp-bridge/result.json
```

## 结果规则

平台结果被规范化为：

- `authenticated`
- `unauthenticated`
- `draft_created`
- `failed`
- `review_required`
- `blocked`
- `unknown`

以下情况硬阻断：

- 上游返回非草稿成功；
- 验证码、扫码或风控；
- 账号或身份不匹配；
- 未知错误；
- 缺少目标平台结果；
- URL 包含凭据或非 HTTP(S) 协议；
- 请求试图启用远程桥接、公开发布或真实执行。

URL 会删除 fragment，以及 Token、Session、Cookie、Signature、API Key 等敏感查询参数。

## 下一阶段

Phase 5.3B 需要用户在本机显式授权后，才允许执行只读握手：

1. 验证目标为回环地址；
2. 检查 Extension 连接状态；
3. 调用 `list_platforms`；
4. 调用单平台 `check_auth`；
5. 生成只读审计包；
6. 不调用 `sync_article`，不创建草稿。
