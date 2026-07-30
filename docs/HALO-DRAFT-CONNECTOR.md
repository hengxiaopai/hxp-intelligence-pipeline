# Halo 官方草稿适配器

## 当前状态

Phase 5.4B 默认只运行进程内 Mock：

```json
{
  "execution_mode": "mock_only",
  "live_execution_enabled": false,
  "network_listener_enabled": false,
  "external_write_performed": false
}
```

它不会访问真实 Halo 站点，不读取 `HXP_HALO_PAT`，也不会生成 Authorization Header。

## 离线链路

```text
website内容包
  + halo-official-draft request
        ↓
Halo draft payload
        ↓
进程内 Mock
        ↓
create_draft_post
update_draft_content
status_lookup
        ↓
DRAFT 审计结果 + 幂等 Ledger
```

`publish`、`release` 和删除操作均被策略阻断。

## 构建草稿载荷

```bash
python scripts/build_halo_draft_payload.py \
  --official-request official-request.json \
  --packages content-packages.json \
  --output halo-draft-payload.json
```

载荷绑定：

- 官方请求 ID；
- 发布条目与网站内容包；
- 内容 SHA-256；
- 按顺序排列的图片 SHA-256；
- Halo 文章标题、Slug、摘要、Markdown 正文；
- `publish=false`；
- PAT 与 Base URL 的环境变量名称。

载荷不包含凭据值。

## 运行本地 Mock

首次执行：

```bash
python scripts/simulate_halo_draft.py \
  --payload halo-draft-payload.json \
  --executed-at 2026-07-30T15:20:00+08:00 \
  --result-output halo-mock-result.json \
  --ledger-output halo-mock-ledger.json
```

幂等重放：

```bash
python scripts/simulate_halo_draft.py \
  --payload halo-draft-payload.json \
  --ledger halo-mock-ledger.json \
  --executed-at 2026-07-30T15:21:00+08:00 \
  --result-output halo-mock-replay.json \
  --ledger-output halo-mock-ledger.next.json
```

相同幂等键和相同载荷返回原 Mock 草稿；相同幂等键但内容不同会硬阻断。

## 签发真实调用授权记录

授权记录本身不会调用站点，也不会启用真实执行：

```bash
python scripts/issue_halo_live_authorization.py \
  --official-request official-request.json \
  --site-origin https://your-halo.example.com \
  --site-fingerprint site-<sha256> \
  --halo-version 2.21.0 \
  --account-ref hxp-halo-owner \
  --issued-at 2026-07-30T15:30:00+08:00 \
  --expires-at 2026-07-30T16:30:00+08:00 \
  --issued-by hengxiaopai \
  --confirm-draft-only \
  --output halo-live-authorization.json
```

授权：

- 最长 60 分钟；
- 一次性；
- 绑定 HTTPS Site Origin 与站点指纹；
- 绑定 Halo 版本、账号引用、请求、内容和图片哈希；
- 动作固定 `draft_only`；
- PAT 只允许来自 `HXP_HALO_PAT` 环境变量；
- `publish_allowed=false`。

## 真实试验前置条件

真实草稿实验尚未实现。进入真实试验还需要主理人单独提供：

1. Halo HTTPS Base URL；
2. Halo 版本；
3. 账号 / Workspace 引用；
4. PAT 已存入本机环境变量的确认；
5. 只创建草稿的明确授权和有效期。

不得在聊天、Issue、日志、Artifact 或仓库中填写 PAT 值。
