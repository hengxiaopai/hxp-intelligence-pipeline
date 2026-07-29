"""Validate human publication decisions without enabling platform writes."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence


class PublicationApprovalError(ValueError):
    """Raised when an approval does not match the exact publication plan."""


CONFIRMATION_FIELDS = (
    "account_ref_confirmed",
    "content_hash_confirmed",
    "asset_hashes_confirmed",
    "asset_order_confirmed",
    "risk_reviewed",
    "action_confirmed",
)


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return (result or "approver")[:40]


def build_publication_approval(
    *,
    plan: Mapping[str, Any],
    decisions: Sequence[Mapping[str, Any]],
    approver_identifier: str,
    approved_at: str,
) -> dict[str, Any]:
    if plan.get("write_actions_enabled") is not False:
        raise PublicationApprovalError("Phase 5.1 禁止开启写入动作")
    entries = {value["entry_id"]: value for value in plan.get("entries", [])}
    if not entries:
        raise PublicationApprovalError("发布计划没有条目")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in decisions:
        entry_id = str(raw.get("entry_id", ""))
        if entry_id not in entries:
            raise PublicationApprovalError(f"审核引用未知发布条目：{entry_id}")
        if entry_id in seen:
            raise PublicationApprovalError(f"发布条目被重复审核：{entry_id}")
        seen.add(entry_id)
        entry = entries[entry_id]
        platform = str(raw.get("platform", ""))
        if platform != entry["platform"]:
            raise PublicationApprovalError(f"平台与发布条目不一致：{entry_id}")
        decision = str(raw.get("decision", ""))
        if decision not in {"approved", "rejected", "blocked"}:
            raise PublicationApprovalError(f"未知审核决定：{entry_id}：{decision}")
        checks = {field: bool(raw.get(field)) for field in CONFIRMATION_FIELDS}
        missing = [field for field in CONFIRMATION_FIELDS if field not in raw]
        if missing:
            raise PublicationApprovalError(f"审核缺少确认项：{entry_id}：{missing}")
        if decision == "approved":
            if entry["approval_status"] == "blocked":
                raise PublicationApprovalError(f"被阻断条目不能审核通过：{entry_id}")
            failed = [field for field, value in checks.items() if not value]
            if failed:
                raise PublicationApprovalError(f"审核通过但确认项未完成：{entry_id}：{failed}")
        normalized.append(
            {
                "entry_id": entry_id,
                "platform": platform,
                "decision": decision,
                **checks,
                "notes": str(raw["notes"]).strip() if raw.get("notes") is not None else None,
            }
        )

    normalized.sort(key=lambda value: value["entry_id"])
    compact = str(plan["plan_id"]).rsplit("-", 1)[-1]
    identifier = str(approver_identifier).strip()
    if not identifier:
        raise PublicationApprovalError("审核者标识不能为空")
    return {
        "schema_version": "1.0.0",
        "approval_id": f"publication-approval-{compact}-{_slug(identifier)}",
        "plan_id": plan["plan_id"],
        "approved_at": approved_at,
        "approver": {"type": "human", "identifier": identifier},
        "decisions": normalized,
        "summary": {
            "total": len(normalized),
            "approved": sum(value["decision"] == "approved" for value in normalized),
            "rejected": sum(value["decision"] == "rejected" for value in normalized),
            "blocked": sum(value["decision"] == "blocked" for value in normalized),
        },
    }


def apply_publication_approval(
    *,
    plan: Mapping[str, Any],
    approval: Mapping[str, Any],
) -> dict[str, Any]:
    if approval.get("plan_id") != plan.get("plan_id"):
        raise PublicationApprovalError("批准记录与发布计划ID不一致")
    decisions = {value["entry_id"]: value for value in approval.get("decisions", [])}
    output = {key: value for key, value in plan.items() if key not in {"entries", "summary"}}
    entries: list[dict[str, Any]] = []
    for original in plan["entries"]:
        entry = dict(original)
        decision = decisions.get(entry["entry_id"])
        if decision is not None:
            entry["approval_status"] = decision["decision"]
        entry["write_allowed"] = False
        entries.append(entry)
    output["entries"] = entries
    output["summary"] = {
        "total": len(entries),
        "pending": sum(value["approval_status"] == "pending" for value in entries),
        "approved": sum(value["approval_status"] == "approved" for value in entries),
        "rejected": sum(value["approval_status"] == "rejected" for value in entries),
        "blocked": sum(value["approval_status"] == "blocked" for value in entries),
    }
    return output
