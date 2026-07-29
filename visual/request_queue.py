"""Build stable AI main-visual requests from a Phase 4.1 visual queue."""

from __future__ import annotations

from typing import Any, Mapping

from .prompt_builder import (
    VisualPromptError,
    build_prompt,
    fingerprint_payload,
    request_fingerprint,
)


class VisualRequestError(ValueError):
    """Raised when a visual request queue cannot be constructed safely."""


DEFAULT_TARGET = {
    "width": 1792,
    "height": 1024,
    "ratio": "16:9",
    "format": "png",
    "text_allowed": False,
}

DEFAULT_SAFE_CROP = {
    "subject_anchor": "upper_center",
    "protected_regions": [
        {"x": 0.12, "y": 0.08, "width": 0.76, "height": 0.78}
    ],
    "notes": "主体保留在中央安全区，左右和底部保留后续9:16、3:4、16:9及2.35:1模板裁切空间。",
}


def _provider_record(config: Mapping[str, Any], provider_id: str) -> Mapping[str, Any]:
    for provider in config.get("providers", []):
        if provider.get("provider_id") == provider_id:
            return provider
    raise VisualRequestError(f"视觉Provider未注册：{provider_id}")


def _assert_provider(config: Mapping[str, Any], provider_id: str) -> None:
    provider = _provider_record(config, provider_id)
    if provider.get("enabled") is not True:
        raise VisualRequestError(f"视觉Provider未启用：{provider_id}")
    if provider_id == "external_api" and provider.get("mode") == "api":
        raise VisualRequestError(
            "external_api默认禁止由核心请求队列启用；请在独立适配器中显式确认环境变量与费用边界"
        )
    if provider.get("credentials_persisted") is not False:
        raise VisualRequestError("Provider配置不得允许持久化凭据")


def _sequence(item_id: str) -> int:
    try:
        return int(item_id.rsplit("-", 1)[1])
    except (IndexError, ValueError) as exc:
        raise VisualRequestError(f"item_id无法解析序号：{item_id}") from exc


def build_visual_request_queue(
    *,
    visual_queue: Mapping[str, Any],
    provider_config: Mapping[str, Any],
    provider_id: str | None = None,
    target: Mapping[str, Any] | None = None,
    safe_crop: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert detail jobs into deterministic no-text visual requests."""
    provider_id = provider_id or str(provider_config.get("default_provider", ""))
    if not provider_id:
        raise VisualRequestError("未配置默认视觉Provider")
    _assert_provider(provider_config, provider_id)

    if visual_queue.get("asset_policy", {}).get("logo_required") is not True:
        raise VisualRequestError("视觉队列缺少品牌资产策略")
    if visual_queue.get("asset_policy", {}).get("detail_visual_required") is not True:
        raise VisualRequestError("视觉队列未声明详情主视觉为必需")

    target_value = dict(target or DEFAULT_TARGET)
    safe_crop_value = dict(safe_crop or DEFAULT_SAFE_CROP)
    requests: list[dict[str, Any]] = []

    jobs = sorted(
        (job for job in visual_queue.get("jobs", []) if job.get("kind") == "detail_9x16"),
        key=lambda job: int(job["order"]),
    )
    if not jobs:
        raise VisualRequestError("视觉队列没有详情海报任务")

    for job in jobs:
        try:
            prompt, negatives, category = build_prompt(job)
        except VisualPromptError as exc:
            raise VisualRequestError(str(exc)) from exc
        attempt = 1
        sequence = _sequence(str(job["item_id"]))
        request_id = (
            f"visual-request-{str(visual_queue['date']).replace('-', '')}-"
            f"{sequence:02d}-a{attempt}"
        )
        fingerprint_input = fingerprint_payload(
            job=job,
            provider=provider_id,
            attempt=attempt,
            prompt=prompt,
            negatives=negatives,
            target=target_value,
            safe_crop=safe_crop_value,
            parent_request_id=None,
        )
        requests.append(
            {
                "request_id": request_id,
                "item_id": job["item_id"],
                "attempt": attempt,
                "parent_request_id": None,
                "request_fingerprint": request_fingerprint(fingerprint_input),
                "provider": provider_id,
                "status": "pending_generation",
                "target": target_value,
                "safe_crop": safe_crop_value,
                "prompt": prompt,
                "negative_constraints": negatives,
                "visual_brief": {
                    "concept": job["visual_brief"]["concept"],
                    "category": category,
                    "must_not_fabricate": list(
                        job["visual_brief"].get("must_not_fabricate", [])
                    ),
                },
                "result": None,
            }
        )

    fingerprints = [request["request_fingerprint"] for request in requests]
    if len(fingerprints) != len(set(fingerprints)):
        raise VisualRequestError("主视觉请求指纹重复")

    compact = str(visual_queue["date"]).replace("-", "")
    external = _provider_record(provider_config, "external_api")
    return {
        "schema_version": "1.0.0",
        "request_queue_id": f"visual-request-queue-{compact}",
        "visual_queue_id": visual_queue["queue_id"],
        "briefing_id": visual_queue["briefing_id"],
        "date": visual_queue["date"],
        "generated_at": visual_queue["generated_at"],
        "provider_policy": {
            "default_provider": provider_id,
            "external_api_enabled": bool(external.get("enabled")),
            "credentials_persisted": False,
            "maximum_attempts": int(provider_config.get("maximum_attempts", 3)),
        },
        "requests": requests,
    }
