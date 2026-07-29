# Phase 5.2 连接器授权与Simulator

## 当前状态

当前阶段只实现连接器安全边界和离线Simulator：

- `real_writes_enabled=false`
- 只有 `simulator-draft` 启用
- 所有真实连接器保持 `enabled=false`
- 只允许 `draft_only`
- 不访问、不登录、不写入任何真实平台
- 凭据值不得进入仓库、日志、Issue、Manifest或Artifact

## 1. 查看连接器能力

```bash
python scripts/inspect_connector_capabilities.py
```

注册表位于 `config/connectors.json`。真实连接器即使已登记，也不会在当前阶段被选择或执行。

## 2. 前置条件

连接器授权只接受已经完成 Phase 5.1 人工确认的发布条目：

```json
{
  "approval_status": "approved",
  "action": "draft_only",
  "write_allowed": false
}
```

`write_allowed=false` 并不代表授权无效，而是证明当前计划本身没有悄悄开启平台写入。Phase 5.2 Simulator仍只做离线演练。

## 3. 签发一次性授权

```bash
python scripts/issue_connector_authorization.py \
  --plan publication-plan.approved.json \
  --connector-id simulator-draft \
  --entry-id publication-entry-20260729-website \
  --account-ref hxp-website-staging \
  --issued-at 2026-07-29T16:00:00+08:00 \
  --expires-at 2026-07-29T17:00:00+08:00 \
  --issued-by hengxiaopai \
  --output connector-authorization.json
```

授权绑定：

- connector ID
- 平台
- 账号引用
- 发布条目
- 幂等键
- 文案 SHA-256
- 按顺序排列的图片 SHA-256
- 动作
- 签发时间和到期时间
- 签发人
- 凭据引用，而非凭据值

任意字段变化后，旧授权都会硬阻断。

## 4. 构建连接器请求

```bash
python scripts/build_connector_request.py \
  --authorization connector-authorization.json \
  --plan publication-plan.approved.json \
  --package-id content-package-20260729-website \
  --account-ref hxp-website-staging \
  --requested-at 2026-07-29T16:30:00+08:00 \
  --request-output connector-request.json \
  --authorization-output connector-authorization.consumed.json
```

构建成功后授权状态变为 `consumed`。同一授权不能再次构建请求。

以下情况立即失败：

- 授权过期、撤销、已消费或尚未生效
- 平台、账号、文案哈希、图片哈希或图片顺序变化
- 发布条目不再是 `approved`
- 动作不是 `draft_only`
- 连接器未启用
- 请求试图启用真实写入
- Simulator携带凭据引用

## 5. 离线模拟草稿

```bash
python scripts/simulate_connector_write.py \
  --request connector-request.json \
  --executed-at 2026-07-29T16:31:00+08:00 \
  --result-output connector-result.json \
  --ledger-output connector-ledger.json
```

结果固定包含：

```json
{
  "connector_mode": "simulator",
  "external_write_performed": false,
  "external_id": null,
  "external_url": null
}
```

Simulator只生成 `simulated_draft_id`，不代表任何平台草稿。

## 6. 幂等重放

使用相同请求和账本再次运行：

```bash
python scripts/simulate_connector_write.py \
  --request connector-request.json \
  --ledger connector-ledger.json \
  --executed-at 2026-07-29T16:32:00+08:00 \
  --result-output connector-result.replay.json \
  --ledger-output connector-ledger.replay.json
```

应返回：

```json
{
  "status": "idempotent_replay"
}
```

账本不会新增第二条记录。相同幂等键但文案、图片顺序、连接器或账号不同会被视为碰撞并硬阻断。

## 7. 授权状态机

允许状态：

```text
issued ──consume──> consumed
   │
   ├──expire──────> expired
   │
   └──revoke──────> revoked
```

`consumed` 不得恢复为 `issued`，也不得再次撤销或复用。

## 8. 真实连接器边界

首个真实连接器接入前，必须再次由主理人明确确认：

- 具体平台和目标账号
- 只创建草稿，还是允许更新草稿
- 凭据来源和有效期
- 允许的动作
- 是否允许状态回查
- 失败后的处理方式

当前代码不会绕过验证码、风控、登录限制、平台协议或人工审核，也不会自动公开发布。
