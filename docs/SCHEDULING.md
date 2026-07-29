# 每日调度、增量水位与历史提交

Phase 3.3 把日报流水线拆成三个安全边界清晰的动作：

1. **计划**：根据来源注册表和水位判断今天应处理哪些来源；
2. **运行**：生成候选池与日报运行包，但不自动推进正式历史；
3. **提交历史**：只有人工审核通过后，才原子更新来源水位和去重索引。

这避免了“任务运行过”被误当成“内容已审核并正式采用”。

## 1. 调度时间

`.github/workflows/daily-pipeline.yml` 使用：

```yaml
cron: "0 1 * * *"
```

即每天北京时间 09:00。中国标准时间没有夏令时，因此固定对应 UTC 01:00。

定时工作流默认只生成采集计划。仓库变量未启用时不会访问任何外部来源。

## 2. 来源计划

```bash
python scripts/plan_daily_run.py \
  --now 2026-07-29T01:00:00Z \
  --mode plan_only \
  --output /tmp/daily-plan.json
```

计划读取：

- `config/sources.json`
- `config/schedule.json`
- `data/state/source-watermarks.json`

计划输出符合 `schemas/daily-plan.schema.json`。

### 到期判断

来源在以下情况进入计划：

- 从未尝试；
- 距离上次尝试已超过最小间隔；
- 距离上次成功已超过最大时效；
- 上次失败，且已超过失败重试等待时间。

排序是确定性的：优先级、到期时间、来源 ID。超过每日数量上限的来源进入 deferred 统计，不会随机变化。

### 行为类型

- `plan_only`：只记录计划，不访问外网；
- `collect_fixture`：使用离线测试文件；
- `collect_live`：显式启用后，访问已注册且允许实时采集的 RSS/HTML；
- `manual_review`：需要人工查看，不由采集器访问。

`requires_auth`、未启用来源、超出优先级范围和不支持的采集方式会进入 blocked 列表。

## 3. 实时采集必须双重显式开启

手动运行工作流时，需要勾选 `live_enabled`；定时任务则要求仓库变量：

```text
HXP_LIVE_COLLECTION_ENABLED=true
```

满足条件后，工作流才会生成 `mode=live` 的计划，并执行：

```bash
python scripts/execute_collection_plan.py \
  --plan /tmp/hxp-plan/daily-plan.json \
  --output-dir /tmp/hxp-raw
```

执行器仍会再次检查：

- `mode=live`；
- `live_enabled=true`；
- 每个来源 `action=collect_live`；
- 每个来源 `live_eligible=true`；
- 来源存在于注册表；
- 原采集器的 HTTPS、DNS、robots、重定向、MIME、超时和响应大小规则。

实时快照只作为工作流 Artifact 保存，不自动提交到正式历史。

## 4. 来源水位

`data/state/source-watermarks.json` 记录：

- 最近尝试时间；
- 最近成功时间；
- 最近成功内容哈希；
- 最近状态；
- 连续失败次数；
- 最近失败指纹。

调度器不会在“生成计划”或“抓取完成”时自动推进正式水位。只有日报被正式采用后，相关来源才记为成功。

## 5. 正式历史提交

默认运行包状态是：

```json
{
  "review_status": "pending",
  "publication_allowed": false
}
```

此时执行以下命令必须失败，且不能修改正式文件：

```bash
python scripts/commit_daily_history.py \
  --run-dir data/daily/2026-07-29 \
  --apply
```

人工审核完成后，先重新生成已批准运行包：

```bash
python scripts/run_daily_pipeline.py \
  --run-dir data/daily/YYYY-MM-DD \
  --mode archived_real_sources \
  --review-status approved
```

先预览历史更新：

```bash
python scripts/commit_daily_history.py \
  --run-dir data/daily/YYYY-MM-DD
```

默认生成：

```text
data/state/source-watermarks.next.json
data/state/dedup-index.next.json
data/daily/YYYY-MM-DD/history-commit.json
```

复核后正式应用：

```bash
python scripts/commit_daily_history.py \
  --run-dir data/daily/YYYY-MM-DD \
  --apply
```

### 提交门槛

必须同时满足：

- `status=validated`；
- `review_status=approved`；
- `publication_allowed=true`；
- `run.json` 中所有 validation 为 true；
- 正式条目能够映射到唯一候选事件；
- 再次执行 3/7/30 天去重后仍为 `select_new` 或 `continuation`。

所有计算和 Schema 校验完成后才写文件。写入使用临时文件替换，避免部分状态已更新、另一部分失败。

### 幂等性

每个正式 `item_id` 只允许进入历史一次。对同一已批准运行重复执行：

- 去重记录数量不增加；
- `item_ids` 不重复；
- 来源水位保持一致；
- `history-commit.json` 标记已提交项目。

## 6. 失败报告

```bash
python scripts/write_failure_report.py \
  --stage collection \
  --error-type CollectionError \
  --message "Authorization: Bearer example token=secret" \
  --source-registry-id registry-github-changelog
```

输出符合 `schemas/failure-report.schema.json`。

报告会清理：

- Authorization Bearer；
- token、API key；
- password、secret；
- Cookie、session；
- URL中的用户名和密码。

失败指纹由阶段、错误类型、清理后的消息和来源 ID 生成。相同指纹在 `failure_issue_cooldown_hours` 内不具备重复建 Issue 的资格。

## 7. GitHub Issue 告警默认关闭

手动工作流需要勾选 `issue_enabled`；定时任务需要仓库变量：

```text
HXP_FAILURE_ISSUES_ENABLED=true
```

即使启用，工作流也只使用清理后的通用错误消息，并在创建前检查是否已有同指纹的开放 Issue。

告警中不包含：

- Token、Cookie和Authorization Header；
- 私密页面正文；
- 原始响应内容；
- 用户输入和邮件等个人数据。

## 8. CI边界

普通 CI：

- 不访问外网；
- 不运行定时工作流；
- 使用固定时间生成两次相同计划并逐字节比较；
- 验证待审核运行无法提交历史；
- 在临时目录测试批准运行的提交与幂等性；
- 验证失败消息脱敏与冷却逻辑。

## 9. 当前仍需人工完成的环节

Phase 3.3 不试图用规则自动理解每个网页的事件动作和对象。以下环节仍需要 ChatGPT 自动化或人工编辑：

- 从原始快照提炼结构化候选；
- 核验高风险事实；
- 判断产品机会和内容角度；
- 批准最终日报；
- 启动正式视觉生产。

这是刻意保留的安全闸门，不是流水线故障。
