"""Build and apply human review decisions for imported AI main visuals."""

from __future__ import annotations

import re
from typing import Any, Mapping


class VisualReviewError(ValueError):
    """Raised when a visual review is incomplete or internally inconsistent."""


REQUIRED_CHECKS = (
    "fact_consistent",
    "brief_consistent",
    "no_text_or_gibberish",
    "no_fabricated_ui_or_data",
    "brand_style_consistent",
    "subject_clear",
    "crop_safe",
    "not_recent_visual_duplicate",
)

VALID_REASONS = {
    "fact_mismatch",
    "subject_mismatch",
    "composition_problem",
    "style_drift",
    "contains_text",
    "fabricated_ui",
    "fabricated_data",
    "logo_or_brand_misuse",
    "unsafe_crop",
    "low_quality",
    "recent_visual_duplicate",
    "other",
}


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    if len(slug) < 3:
        slug = "reviewer"
    return slug[:40]


def _request_map(request_queue: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for request in request_queue.get("requests", []):
        request_id = str(request["request_id"])
        if request_id in result:
            raise VisualReviewError(f"请求ID重复：{request_id}")
        result[request_id] = request
    return result


def _normalize_decision(
    decision: Mapping[str, Any],
    request: Mapping[str, Any],
) -> dict[str, Any]:
    if request.get("result") is None:
        raise VisualReviewError(f"请求尚未导入主视觉：{request['request_id']}")
    status = str(decision.get("decision", ""))
    if status not in {"approved", "rejected", "needs_changes"}:
        raise VisualReviewError(f"无效审核决定：{request['request_id']}：{status}")

    supplied_checks = decision.get("checks", {})
    checks = {name: bool(supplied_checks.get(name)) for name in REQUIRED_CHECKS}
    missing = [name for name in REQUIRED_CHECKS if name not in supplied_checks]
    if missing:
        raise VisualReviewError(
            f"审核缺少检查项：{request['request_id']}：{', '.join(missing)}"
        )

    reasons = list(dict.fromkeys(str(value) for value in decision.get("rejection_reasons", [])))
    invalid = sorted(set(reasons).difference(VALID_REASONS))
    if invalid:
        raise VisualReviewError(
            f"审核包含未知驳回原因：{request['request_id']}：{invalid}"
        )
    change_instruction = decision.get("change_instruction")
    notes = decision.get("notes")

    if status == "approved":
        failed = [name for name, value in checks.items() if not value]
        if failed:
            raise VisualReviewError(
                f"审核通过但检查项失败：{request['request_id']}：{failed}"
            )
        if reasons:
            raise VisualReviewError(
                f"审核通过不得保留驳回原因：{request['request_id']}"
            )
        change_instruction = None
    else:
        if all(checks.values()):
            raise VisualReviewError(
                f"驳回或修改必须至少有一个失败检查项：{request['request_id']}"
            )
        if not reasons:
            raise VisualReviewError(
                f"驳回或修改必须填写原因：{request['request_id']}"
            )
        if status == "needs_changes" and not str(change_instruction or "").strip():
            raise VisualReviewError(
                f"needs_changes必须填写定向修改说明：{request['request_id']}"
            )

    return {
        "request_id": request["request_id"],
        "item_id": request["item_id"],
        "asset_sha256": request["result"]["sha256"],
        "decision": status,
        "checks": checks,
        "rejection_reasons": reasons,
        "change_instruction": (
            str(change_instruction).strip() if change_instruction is not None else None
        ),
        "notes": str(notes).strip() if notes is not None else None,
    }


def build_review_batch(
    *,
    request_queue: Mapping[str, Any],
    decisions: list[Mapping[str, Any]],
    reviewer_type: str,
    reviewer_identifier: str,
    reviewed_at: str,
) -> dict[str, Any]:
    """Validate decisions and produce a deterministic review batch."""
    if reviewer_type not in {"human", "fixture"}:
        raise VisualReviewError(f"无效审核者类型：{reviewer_type}")
    identifier = str(reviewer_identifier).strip()
    if not identifier:
        raise VisualReviewError("审核者标识不能为空")
    if not reviewed_at:
        raise VisualReviewError("reviewed_at不能为空")

    requests = _request_map(request_queue)
    reviews: list[dict[str, Any]] = []
    seen: set[str] = set()
    for decision in decisions:
        request_id = str(decision.get("request_id", ""))
        if request_id not in requests:
            raise VisualReviewError(f"审核引用未知请求：{request_id}")
        if request_id in seen:
            raise VisualReviewError(f"同一请求被重复审核：{request_id}")
        seen.add(request_id)
        reviews.append(_normalize_decision(decision, requests[request_id]))

    if not reviews:
        raise VisualReviewError("审核批次不能为空")
    reviews.sort(key=lambda value: value["request_id"])
    compact = str(request_queue["date"]).replace("-", "")
    summary = {
        "total": len(reviews),
        "approved": sum(value["decision"] == "approved" for value in reviews),
        "rejected": sum(value["decision"] == "rejected" for value in reviews),
        "needs_changes": sum(
            value["decision"] == "needs_changes" for value in reviews
        ),
    }
    return {
        "schema_version": "1.0.0",
        "review_batch_id": f"visual-review-{compact}-{_slug(identifier)}",
        "request_queue_id": request_queue["request_queue_id"],
        "reviewed_at": reviewed_at,
        "reviewer": {"type": reviewer_type, "identifier": identifier},
        "reviews": reviews,
        "summary": summary,
    }


def apply_review_batch(
    *,
    request_queue: Mapping[str, Any],
    review_batch: Mapping[str, Any],
) -> dict[str, Any]:
    """Copy a request queue and apply review states to exact request IDs."""
    if review_batch.get("request_queue_id") != request_queue.get("request_queue_id"):
        raise VisualReviewError("审核批次与请求队列ID不一致")
    decisions = {value["request_id"]: value for value in review_batch["reviews"]}
    output = {key: value for key, value in request_queue.items() if key != "requests"}
    requests: list[dict[str, Any]] = []
    for original in request_queue["requests"]:
        request = dict(original)
        decision = decisions.get(request["request_id"])
        if decision is not None:
            if request.get("result", {}).get("sha256") != decision["asset_sha256"]:
                raise VisualReviewError(
                    f"审核资产哈希与请求结果不一致：{request['request_id']}"
                )
            request["status"] = {
                "approved": "approved",
                "rejected": "rejected",
                "needs_changes": "needs_review",
            }[decision["decision"]]
        requests.append(request)
    output["requests"] = requests
    return output
