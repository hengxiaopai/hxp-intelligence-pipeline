# 每日端到端运行包

Phase 3.2 将来源记录、候选池、编辑评分、正式简报和运行清单保存在同一个日期目录中，使每份日报都能被重放、复核和审计。

## 目录结构

```text
data/daily/YYYY-MM-DD/
├── sources/
│   ├── src-*.json
│   └── ...
├── candidate-pool.json
├── editorial-scores.json
├── briefing.json
├── briefing.md
└── run.json
```

首份真实来源运行位于：

```text
data/daily/2026-07-29/
```

## 文件职责

### `sources/*.json`

每个来源独立保存，符合 `schemas/source.schema.json`。记录完整 URL、发布和检索时间、来源类型、权威等级、证据摘要、验证状态及冲突。

这些文件是结构化证据记录，不是完整网页镜像。事实核验仍应回到原始官方页面。

### `candidate-pool.json`

保存候选事实、证据声明、去重动作、编辑评分输入、公开文案和转化机会。它可以包含最终被淘汰的重复或低置信度候选。

### `editorial-scores.json`

由 `scripts/score_candidates.py` 确定性生成，符合 `schemas/editorial-score.schema.json`。

### `briefing.json`

由 `scripts/assemble_briefing.py` 生成，符合 `schemas/briefing.schema.json`。允许保留内部 `rejected_candidates` 作为审计记录。

### `briefing.md`

公开版简报。不得包含候选 ID、内部淘汰池或未公开审核信息。

### `run.json`

符合 `schemas/daily-run.schema.json`，记录：

- 运行日期、模式和审核状态；
- 来源数量与最终入选数量；
- 所有输入、输出和来源文件的 SHA-256；
- Schema、引用、哈希、公开 Markdown 和确定性重放检查；
- 是否允许发布。

## 运行

候选池和来源记录准备完成后：

```bash
python scripts/run_daily_pipeline.py \
  --run-dir data/daily/YYYY-MM-DD \
  --mode archived_real_sources \
  --review-status pending
```

该命令会生成或覆盖：

- `editorial-scores.json`
- `briefing.json`
- `briefing.md`
- `run.json`

它不会访问外网，不会更新去重历史，不会生图，也不会自动发布。

## 验证与重放

```bash
python scripts/validate_daily_run.py \
  --run-dir data/daily/YYYY-MM-DD
```

验证器会：

1. 校验 `run.json`；
2. 检查全部文件是否存在且哈希、字节数一致；
3. 校验所有来源记录、候选、评分和简报 Schema；
4. 检查候选引用的来源是否完整，是否存在未使用来源；
5. 确认公开 Markdown 不包含内部标记；
6. 在临时目录重放评分与组装，确认输出逐字节一致。

## 审核和发布状态

默认运行：

```json
{
  "review_status": "pending",
  "publication_allowed": false
}
```

即使所有自动校验通过，只要人工审核尚未批准，就不能进入正式发布或海报生成。

人工审核完成后重新运行：

```bash
python scripts/run_daily_pipeline.py \
  --run-dir data/daily/YYYY-MM-DD \
  --mode archived_real_sources \
  --review-status approved
```

`publication_allowed=true` 只表示结构化内容满足进入视觉阶段的门槛，不代表已经自动发布。

## 2026-07-29 首次运行结果

首次真实来源运行归档了 6 个官方来源，形成 7 个候选：

- 5 条进入今日新增事实；
- 1 条因与完整治理主题重复而淘汰；
- 1 条因把任务跨界外推为岗位消失、证据不足而淘汰；
- 0 条延续跟踪。

运行保持 `review_status=pending`，因此正式发布入口关闭。

## 事实边界

- OpenAI工作研究只支持“任务跨越职业边界”，不支持“专业岗位已经消失”；
- GitHub安全和Copilot更新只描述官方已经公布的功能与适用范围；
- 相近的Copilot App访问策略和托管设置被合并为一条企业治理主题，避免拆成重复热点；
- 首次运行未强行加入A股条目，因为当时没有在运行包中完成同等强度的一手公告核验。

## 后续调度

Phase 3.3 将在此基础上增加：

- 日期化调度；
- 来源增量更新；
- 成功后提交去重历史；
- 失败告警和重试；
- 等待人工批准的视觉任务队列。
