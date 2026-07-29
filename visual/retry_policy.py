"""Create and apply targeted retry plans for rejected AI main visuals."""

from __future__ import annotations

import re
from typing import Any, Mapping

from .prompt_builder import request_fingerprint


class VisualRetryError(ValueError):
    """Raised when a retry plan cannot be produced or applied safely."""


REASON_INSTRUCTIONS = {
    "subject_mismatch": "只修正主体：严格使用视觉概念中的主体和关系，不添加无关人物、设备或场景。",
    "composition_problem": "只修正构图：强化单一视觉中心、中央安全区和四种比例的裁切余量，减少杂乱元素。",
    "style_drift": "只修正风格：回到明亮蓝白科技、编辑式白底、冰蓝玻璃与克制高级感，禁止赛博朋克和光污染。",
    "contains_text": "移除画面中全部文字、数字、字母、标签、Logo、水印和伪文字，任何可读或不可读字符都不得出现。",
    "fabricated_ui": "移除所有仿造产品截图、官方界面、仪表盘、终端窗口和社交媒体页面，仅保留抽象视觉隐喻。",
    "fabricated_data": "移除所有虚构图表、刻度、百分比、金额、排名和统计数据，不新增事实摘要之外的信息。",
    "logo_or_brand_misuse": "移除所有品牌标识和Logo，正式珩小派Logo只由后续固定模板嵌入。",
    "unsafe_crop": "把主体收回中央安全区，扩大四周留白，确保9:16、3:4、16:9和2.35:1均可独立排版。",
    "low_quality": "提高材质、光线、结构与边缘细节质量，保持真实可构建和高端研究报告封面质感。",
    "recent_visual_duplicate": "更换视觉隐喻与空间结构，避免复用最近30天相似的轨道、球体、中心网络或相同镜头。",
    "other": "按照人工审核说明做最小范围修正，不改变已经正确的事实、主体和品牌方向。",
}


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return (slug or "batch")[:40]


def _request_map(request_queue: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for request in request_queue.get("requests", []):
        request_id = str(request["request_id"])
        if request_id in result:
            raise VisualRetryError(f"请求ID重复：{request_id}")
        result[request_id] = request
    return result


def _choose_reason(review: Mapping[str, Any]) -> str:
    reasons = list(review.get("rejection_reasons", []))
    if "fact_mismatch" in reasons:
        return "fact_mismatch"
    for reason in reasons:
        if reason in REASON_INSTRUCTIONS:
            return str(reason)
    return "other"


def _prompt_delta(review: Mapping[str, Any], reason: str) -> str:
    if reason == "fact_mismatch":
        return "事实或标题与来源不一致，禁止通过重生图片掩盖；退回编辑阶段核验并重新生成简报。"
    base = REASON_INSTRUCTIONS[reason]
    instruction = str(review.get("change_instruction") or "").strip()
    if instruction:
        return f"{base} 人工定向要求：{instruction}"
    return base


def _new_request(parent: Mapping[str, Any], prompt_delta: str) -> dict[str, Any]:
    attempt = int(parent["attempt"]) + 1
    request_id = str(parent["request_id"]).rsplit("-a", 1)[0] + f"-a{attempt}"
    prompt = str(parent["prompt"]).rstrip() + "\n重试修正（只修改下列问题）：" + prompt_delta
    payload = {
        "item_id": parent["item_id"],
        "provider": parent["provider"],
        "attempt": attempt,
        "parent_request_id": parent["request_id"],
        "prompt": prompt,
        "negative_constraints": parent["negative_constraints"],
        "target": parent["target"],
        "safe_crop": parent["safe_crop"],
        "visual_brief": parent["visual_brief"],
    }
    return {
        "request_id": request_id,
        "item_id": parent["item_id"],
        "attempt": attempt,
        "parent_request_id": parent["request_id"],
        "request_fingerprint": request_fingerprint(payload),
        "provider": parent["provider"],
        "status": "pending_generation",
        "target": parent["target"],
        "safe_crop": parent["safe_crop"],
        "prompt": prompt,
        "negative_constraints": parent["negative_constraints"],
        "visual_brief": parent["visual_brief"],
        "result": None,
    }


def build_retry_plan(
    *,
    request_queue: Mapping[str, Any],
    review_batch: Mapping[str, Any],
    generated_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Return a retry plan and scheduled request objects keyed by next request ID."""
    if review_batch.get("request_queue_id") != request_queue.get("request_queue_id"):
        raise VisualRetryError("审核批次与请求队列ID不一致")
    generated_at = generated_at or str(review_batch.get("reviewed_at", ""))
    if not generated_at:
        raise VisualRetryError("重试计划缺少generated_at")

    maximum_attempts = int(
        request_queue.get("provider_policy", {}).get("maximum_attempts", 3)
    )
    requests = _request_map(request_queue)
    existing_fingerprints = {
        str(value["request_fingerprint"]) for value in requests.values()
    }
    retries: list[dict[str, Any]] = []
    scheduled_requests: dict[str, dict[str, Any]] = {}
    eligible = 0

    for review in sorted(review_batch.get("reviews", []), key=lambda value: value["request_id"]):
        if review["decision"] == "approved":
            continue
        eligible += 1
        parent_id = str(review["request_id"])
        if parent_id not in requests:
            raise VisualRetryError(f"审核引用未知父请求：{parent_id}")
        parent = requests[parent_id]
        reason = _choose_reason(review)
        delta = _prompt_delta(review, reason)
        next_attempt = int(parent["attempt"]) + 1

        if reason == "fact_mismatch":
            retries.append(
                {
                    "item_id": parent["item_id"],
                    "parent_request_id": parent_id,
                    "next_request_id": None,
                    "next_attempt": next_attempt,
                    "retry_reason": reason,
                    "prompt_delta": delta,
                    "new_request_fingerprint": None,
                    "decision": "editorial_blocked",
                }
            )
            continue

        if next_attempt > maximum_attempts:
            retries.append(
                {
                    "item_id": parent["item_id"],
                    "parent_request_id": parent_id,
                    "next_request_id": None,
                    "next_attempt": next_attempt,
                    "retry_reason": reason,
                    "prompt_delta": delta,
                    "new_request_fingerprint": None,
                    "decision": "exhausted",
                }
            )
            continue

        next_request = _new_request(parent, delta)
        fingerprint = next_request["request_fingerprint"]
        if fingerprint in existing_fingerprints:
            retries.append(
                {
                    "item_id": parent["item_id"],
                    "parent_request_id": parent_id,
                    "next_request_id": None,
                    "next_attempt": next_attempt,
                    "retry_reason": reason,
                    "prompt_delta": delta,
                    "new_request_fingerprint": fingerprint,
                    "decision": "blocked_unchanged",
                }
            )
            continue

        existing_fingerprints.add(fingerprint)
        scheduled_requests[next_request["request_id"]] = next_request
        retries.append(
            {
                "item_id": parent["item_id"],
                "parent_request_id": parent_id,
                "next_request_id": next_request["request_id"],
                "next_attempt": next_attempt,
                "retry_reason": reason,
                "prompt_delta": delta,
                "new_request_fingerprint": fingerprint,
                "decision": "schedule",
            }
        )

    compact = str(request_queue["date"]).replace("-", "")
    plan = {
        "schema_version": "1.0.0",
        "retry_plan_id": f"visual-retry-{compact}-{_slug(str(review_batch['review_batch_id']).rsplit('-', 1)[-1])}",
        "request_queue_id": request_queue["request_queue_id"],
        "review_batch_id": review_batch["review_batch_id"],
        "generated_at": generated_at,
        "maximum_attempts": maximum_attempts,
        "retries": retries,
        "summary": {
            "eligible": eligible,
            "scheduled": sum(value["decision"] == "schedule" for value in retries),
            "exhausted": sum(value["decision"] == "exhausted" for value in retries),
            "blocked_unchanged": sum(
                value["decision"] == "blocked_unchanged" for value in retries
            ),
            "editorial_blocked": sum(
                value["decision"] == "editorial_blocked" for value in retries
            ),
        },
    }
    return plan, scheduled_requests


def apply_retry_plan(
    *,
    request_queue: Mapping[str, Any],
    retry_plan: Mapping[str, Any],
    scheduled_requests: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Append only scheduled retry requests without overwriting prior attempts."""
    if retry_plan.get("request_queue_id") != request_queue.get("request_queue_id"):
        raise VisualRetryError("重试计划与请求队列ID不一致")
    expected_ids = {
        str(value["next_request_id"])
        for value in retry_plan.get("retries", [])
        if value["decision"] == "schedule"
    }
    if expected_ids != set(scheduled_requests):
        raise VisualRetryError("重试计划与待追加请求集合不一致")

    existing_ids = {str(value["request_id"]) for value in request_queue["requests"]}
    if existing_ids.intersection(expected_ids):
        raise VisualRetryError("重试请求ID已存在，禁止覆盖旧审计记录")

    output = {key: value for key, value in request_queue.items() if key != "requests"}
    combined = [dict(value) for value in request_queue["requests"]]
    combined.extend(dict(scheduled_requests[key]) for key in sorted(expected_ids))
    output["requests"] = combined
    return output
