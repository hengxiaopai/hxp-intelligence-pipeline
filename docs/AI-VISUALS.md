# AI 主视觉生成、导入、审核与定向重试

## 设计原则

图片模型只负责生成**无文字主视觉**。以下内容始终由固定模板负责：

- 中文标题、摘要和分析；
- 日期、编号和来源；
- 珩小派正式 Logo；
- 真实数据、图表和产品界面。

这样可以避免中文错字、Logo 变形、数字错误和系列版式漂移。

## 1. 生成主视觉请求

```bash
python scripts/build_visual_requests.py \
  --visual-queue data/daily/YYYY-MM-DD/visual/queue.json \
  --provider manual_chatgpt \
  --output data/daily/YYYY-MM-DD/visual/requests.json
```

每条详情情报生成一个稳定请求，包含：

- `request_id`、`item_id` 和尝试次数；
- 稳定 `request_fingerprint`；
- 1792×1024、16:9、PNG 目标；
- 视觉概念、品牌方向和安全裁切区域；
- 禁止文字、Logo、虚构 UI、虚构数据和虚构合作关系；
- `must_not_fabricate` 事实边界。

相同输入会生成相同提示词和请求指纹。

## 2. 交给 ChatGPT 图片生成

默认 Provider 是 `manual_chatgpt`。将每个请求中的 `prompt` 分别交给 ChatGPT 图片生成。

保存文件时使用请求 ID：

```text
visual-request-YYYYMMDD-01-a1.png
visual-request-YYYYMMDD-02-a1.png
...
```

第一次尝试也兼容使用 `item_id.png`，但从第二次尝试起必须使用请求 ID，避免覆盖旧版本。

图片必须：

- 不含任何中文、英文单词、数字、Logo 或水印；
- 主体位于中央安全区域，允许后续适配横竖比例；
- 符合明亮蓝白科技、Quiet Intelligence、编辑式高端科技风；
- 不伪造事件现场、产品截图、财务图表或合作关系。

## 3. 导入生成结果

```bash
python scripts/import_visual_results.py \
  --requests data/daily/YYYY-MM-DD/visual/requests.json \
  --result-dir visual-results/YYYY-MM-DD \
  --generator-reference chatgpt-manual-YYYYMMDD \
  --output data/daily/YYYY-MM-DD/visual/requests.imported.json
```

导入器检查：

- 文件名与请求匹配；
- 图片格式；
- 1792×1024 精确尺寸；
- SHA-256 和字节数；
- MIME 类型；
- 生成任务引用不得包含 API Key、Bearer、Cookie、Token 或 Session。

仓库不保存图片服务凭据和原始私密响应。

## 4. 人工审核

准备审核决定文件：

```json
{
  "reviewed_at": "2026-07-29T15:00:00+08:00",
  "reviewer": {
    "type": "human",
    "identifier": "hengxiaopai"
  },
  "decisions": [
    {
      "request_id": "visual-request-20260729-01-a1",
      "decision": "approved",
      "checks": {
        "fact_consistent": true,
        "brief_consistent": true,
        "no_text_or_gibberish": true,
        "no_fabricated_ui_or_data": true,
        "brand_style_consistent": true,
        "subject_clear": true,
        "crop_safe": true,
        "not_recent_visual_duplicate": true
      },
      "rejection_reasons": [],
      "change_instruction": null,
      "notes": null
    }
  ]
}
```

执行：

```bash
python scripts/review_visuals.py \
  --requests data/daily/YYYY-MM-DD/visual/requests.imported.json \
  --decisions data/daily/YYYY-MM-DD/visual/review-decisions.json \
  --review-output data/daily/YYYY-MM-DD/visual/review.json \
  --requests-output data/daily/YYYY-MM-DD/visual/requests.reviewed.json
```

审核通过要求八个检查项全部为 `true`。

## 5. 定向重试

```bash
python scripts/retry_failed_visuals.py \
  --requests data/daily/YYYY-MM-DD/visual/requests.reviewed.json \
  --review data/daily/YYYY-MM-DD/visual/review.json \
  --generated-at 2026-07-29T15:10:00+08:00 \
  --plan-output data/daily/YYYY-MM-DD/visual/retry-plan.json \
  --requests-output data/daily/YYYY-MM-DD/visual/requests.retried.json
```

重试规则：

- 只为 `rejected`、`needs_changes` 或生成失败的条目创建新请求；
- 新请求保留 `parent_request_id`；
- 新请求尝试次数递增；
- 提示词必须包含明确 `prompt_delta`；
- 旧请求、旧图片和旧审核记录不得覆盖；
- 同一失败指纹且提示词无变化时禁止重复执行；
- 默认最多三次总尝试。

### 错误路由

- 构图、主体、风格、文字、裁切问题：进入图片定向重试；
- 事实不一致：`editorial_block`，退回编辑和来源核验；
- 虚构数据或虚构 UI：驳回并加强禁止项；
- 最近 30 天视觉重复：更换构图隐喻，不改变事实内容。

## 6. 选择正式主视觉

多平台导出时，系统会按 `item_id`：

1. 查找人工审核为 `approved` 的请求；
2. 核对审核哈希与图片结果哈希；
3. 核对请求状态已应用为 `approved`；
4. 当存在多个已批准尝试时，选择尝试次数最高的一张；
5. 缺少任一条正式主视觉时整体阻断。

## Provider 边界

`config/visual-providers.json` 当前包含：

- `manual_chatgpt`：默认启用，无凭据；
- `fixture`：仅用于 CI；
- `external_api`：默认关闭，需要显式适配器和环境变量。

任何外部 API 适配器都必须：

- 显式启用；
- 从环境变量读取密钥；
- 不在日志、JSON、Manifest 或失败报告中保存凭据；
- 不把原始私密响应提交到仓库；
- 提供请求 ID、结果哈希和可审计任务引用。
