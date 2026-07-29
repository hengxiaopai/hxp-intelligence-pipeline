"""Build a no-write publication plan with deterministic idempotency keys."""

from __future__ import annotations

from typing import Any, Mapping

from .platform_rules import canonical_hash


class PublicationPlanError(ValueError):
    """Raised when content packages cannot safely enter a publication plan."""


def build_publication_plan(
    *,
    package_batch: Mapping[str, Any],
    created_at: str,
) -> dict[str, Any]:
    if package_batch.get("write_actions_enabled") is not False:
        raise PublicationPlanError("Phase 5.1 内容包必须保持 write_actions_enabled=false")
    compact = str(package_batch["date"]).replace("-", "")
    packages = {value["platform"]: value for value in package_batch.get("packages", [])}
    expected = ("wechat", "xiaohongshu", "douyin", "x", "website")
    if set(packages) != set(expected):
        raise PublicationPlanError("发布计划需要五个平台内容包")

    entries: list[dict[str, Any]] = []
    for platform in expected:
        package = packages[platform]
        asset_hashes = [value["sha256"] for value in package["assets"]]
        blocked = package["status"] != "validated" or not all(
            package["validations"].values()
        )
        idempotency_material = {
            "package_id": package["package_id"],
            "content_hash": package["content_hash"],
            "asset_hashes": asset_hashes,
            "action": "draft_only",
        }
        entries.append(
            {
                "entry_id": f"publication-entry-{compact}-{platform}",
                "platform": platform,
                "package_id": package["package_id"],
                "account_ref": None,
                "action": "draft_only",
                "approval_status": "blocked" if blocked else "pending",
                "idempotency_key": "pub-" + canonical_hash(idempotency_material)[:48],
                "content_hash": package["content_hash"],
                "asset_hashes": asset_hashes,
                "scheduled_at": None,
                "risk_flags": package["risk_flags"],
                "write_allowed": False,
            }
        )

    return {
        "schema_version": "1.0.0",
        "plan_id": f"publication-plan-{compact}",
        "package_batch_id": package_batch["package_batch_id"],
        "created_at": created_at,
        "default_action": "draft_only",
        "write_actions_enabled": False,
        "entries": entries,
        "summary": {
            "total": len(entries),
            "pending": sum(value["approval_status"] == "pending" for value in entries),
            "approved": 0,
            "rejected": 0,
            "blocked": sum(value["approval_status"] == "blocked" for value in entries),
        },
    }
