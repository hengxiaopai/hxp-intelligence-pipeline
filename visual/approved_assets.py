"""Resolve the latest human-approved main visual for every detail item."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


class ApprovedAssetError(ValueError):
    """Raised when an approved visual cannot be resolved or verified."""


def _request_map(request_queue: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    requests: dict[str, Mapping[str, Any]] = {}
    for request in request_queue.get("requests", []):
        request_id = str(request["request_id"])
        if request_id in requests:
            raise ApprovedAssetError(f"主视觉请求ID重复：{request_id}")
        requests[request_id] = request
    return requests


def resolve_result_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[1] / path


def select_latest_approved_assets(
    *,
    visual_queue: Mapping[str, Any],
    request_queue: Mapping[str, Any],
    review_batch: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return one latest approved request/result record for each detail job item."""
    if request_queue.get("visual_queue_id") != visual_queue.get("queue_id"):
        raise ApprovedAssetError("主视觉请求队列与视觉队列ID不一致")
    if review_batch.get("request_queue_id") != request_queue.get("request_queue_id"):
        raise ApprovedAssetError("人工审核批次与主视觉请求队列ID不一致")

    requests = _request_map(request_queue)
    approved: dict[str, list[dict[str, Any]]] = {}
    for review in review_batch.get("reviews", []):
        if review.get("decision") != "approved":
            continue
        request_id = str(review["request_id"])
        request = requests.get(request_id)
        if request is None:
            raise ApprovedAssetError(f"审核引用未知主视觉请求：{request_id}")
        result = request.get("result")
        if result is None:
            raise ApprovedAssetError(f"审核通过的请求缺少图片结果：{request_id}")
        if str(result.get("sha256")) != str(review.get("asset_sha256")):
            raise ApprovedAssetError(f"审核哈希与图片结果不一致：{request_id}")
        if request.get("status") != "approved":
            raise ApprovedAssetError(f"审核通过的请求状态尚未应用：{request_id}")

        path = resolve_result_path(str(result["path"]))
        if not path.is_file():
            raise ApprovedAssetError(f"审核通过的主视觉文件不存在：{path}")
        approved.setdefault(str(request["item_id"]), []).append(
            {
                "request_id": request_id,
                "attempt": int(request["attempt"]),
                "item_id": str(request["item_id"]),
                "path": path,
                "sha256": str(result["sha256"]),
                "width": int(result["width"]),
                "height": int(result["height"]),
                "mime_type": str(result["mime_type"]),
            }
        )

    selected: dict[str, dict[str, Any]] = {}
    detail_items = [
        str(job["item_id"])
        for job in visual_queue.get("jobs", [])
        if job.get("item_id") is not None
    ]
    for item_id in detail_items:
        candidates = approved.get(item_id, [])
        if not candidates:
            raise ApprovedAssetError(f"详情条目缺少人工审核通过的主视觉：{item_id}")
        candidates.sort(key=lambda value: (value["attempt"], value["request_id"]))
        selected[item_id] = candidates[-1]

    return selected
