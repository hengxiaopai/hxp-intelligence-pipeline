"""Deterministic, registry-driven scheduling for the HXP daily pipeline."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence


class SchedulerError(ValueError):
    """Raised when scheduler inputs are invalid."""


def parse_datetime(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise SchedulerError(f"时间格式无效：{value}") from exc
    if parsed.tzinfo is None:
        raise SchedulerError(f"时间必须包含时区：{value}")
    return parsed.astimezone(timezone.utc)


def format_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        raise SchedulerError("时间必须包含时区")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _state_by_id(state: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for item in state.get("sources", []):
        registry_id = str(item["registry_id"])
        if registry_id in result:
            raise SchedulerError(f"来源水位 ID 重复：{registry_id}")
        result[registry_id] = item
    return result


def _default_state(registry_id: str) -> dict[str, Any]:
    return {
        "registry_id": registry_id,
        "last_attempt_at": None,
        "last_success_at": None,
        "last_content_hash": None,
        "last_status": "never",
        "consecutive_failures": 0,
        "last_failure_fingerprint": None,
    }


def _elapsed(now: datetime, value: str | None) -> timedelta | None:
    if not value:
        return None
    return now - parse_datetime(value)


def _due_status(
    source: Mapping[str, Any],
    source_state: Mapping[str, Any],
    config: Mapping[str, Any],
    now: datetime,
) -> tuple[bool, str | None, str | None]:
    last_attempt = source_state.get("last_attempt_at")
    last_success = source_state.get("last_success_at")
    status = source_state.get("last_status", "never")

    if not last_attempt:
        return True, "never_attempted", None

    attempt_elapsed = _elapsed(now, str(last_attempt))
    if attempt_elapsed is None or attempt_elapsed.total_seconds() < 0:
        raise SchedulerError(
            f"来源水位时间晚于当前时间：{source['registry_id']} -> {last_attempt}"
        )

    if status == "failure":
        retry_minutes = int(config["failure_retry_minutes"])
        due_at = parse_datetime(str(last_attempt)) + timedelta(minutes=retry_minutes)
        if now >= due_at:
            return True, "retry_after_failure", format_datetime(due_at)
        return False, None, format_datetime(due_at)

    minimum = timedelta(minutes=int(source["min_interval_minutes"]))
    due_at = parse_datetime(str(last_attempt)) + minimum
    if now < due_at:
        return False, None, format_datetime(due_at)

    if last_success:
        success_elapsed = _elapsed(now, str(last_success))
        if success_elapsed is None or success_elapsed.total_seconds() < 0:
            raise SchedulerError(
                f"来源成功时间晚于当前时间：{source['registry_id']} -> {last_success}"
            )
        maximum_age = timedelta(hours=int(source["max_age_hours"]))
        if success_elapsed >= maximum_age:
            freshness_due = parse_datetime(str(last_success)) + maximum_age
            return True, "freshness_deadline_exceeded", format_datetime(freshness_due)

    return True, "minimum_interval_elapsed", format_datetime(due_at)


def _live_eligibility(
    source: Mapping[str, Any],
    config: Mapping[str, Any],
    live_enabled: bool,
) -> bool:
    if not live_enabled:
        return False
    if source.get("requires_auth"):
        return False
    if source.get("collection_method") not in set(config["allowed_live_methods"]):
        return False
    if source.get("access_policy") in set(config["blocked_live_access_policies"]):
        return False
    return True


def _action_for(
    source: Mapping[str, Any],
    *,
    mode: str,
    live_eligible: bool,
) -> str:
    method = source["collection_method"]
    policy = source["access_policy"]
    if method == "manual_review" or policy == "manual_only":
        return "manual_review"
    if mode == "fixture":
        return "collect_fixture"
    if mode == "live" and live_eligible:
        return "collect_live"
    return "plan_only"


def build_daily_plan(
    *,
    registry: Mapping[str, Any],
    state: Mapping[str, Any],
    config: Mapping[str, Any],
    now: datetime,
    mode: str = "plan_only",
    live_enabled: bool = False,
) -> dict[str, Any]:
    """Build a stable plan from explicit time, registry, state, and policy."""
    if mode not in {"plan_only", "fixture", "live"}:
        raise SchedulerError(f"不支持的调度模式：{mode}")
    if now.tzinfo is None:
        raise SchedulerError("now 必须包含时区")
    observed = now.astimezone(timezone.utc)
    states = _state_by_id(state)
    maximum_priority = int(config["max_priority"])
    supported_methods = {"rss", "html_index", "manual_review", "official_api"}

    blocked: list[dict[str, str]] = []
    due_candidates: list[dict[str, Any]] = []
    not_due = 0
    active_count = 0

    seen_registry_ids: set[str] = set()
    for source in registry.get("sources", []):
        registry_id = str(source["registry_id"])
        if registry_id in seen_registry_ids:
            raise SchedulerError(f"来源注册 ID 重复：{registry_id}")
        seen_registry_ids.add(registry_id)

        if not source.get("active", False):
            blocked.append({"registry_id": registry_id, "reason": "inactive"})
            continue
        active_count += 1

        if int(source["priority"]) > maximum_priority:
            blocked.append({"registry_id": registry_id, "reason": "priority_excluded"})
            continue
        if source.get("requires_auth"):
            blocked.append({"registry_id": registry_id, "reason": "requires_auth"})
            continue
        if source.get("collection_method") not in supported_methods:
            blocked.append(
                {"registry_id": registry_id, "reason": "unsupported_collection_method"}
            )
            continue

        current_state = states.get(registry_id, _default_state(registry_id))
        due, due_reason, due_since = _due_status(source, current_state, config, observed)
        if not due:
            not_due += 1
            continue

        live_eligible = _live_eligibility(source, config, live_enabled)
        due_candidates.append(
            {
                "registry_id": registry_id,
                "priority": int(source["priority"]),
                "collection_method": source["collection_method"],
                "access_policy": source["access_policy"],
                "action": _action_for(
                    source,
                    mode=mode,
                    live_eligible=live_eligible,
                ),
                "due_reason": due_reason,
                "due_since": due_since,
                "last_attempt_at": current_state.get("last_attempt_at"),
                "last_success_at": current_state.get("last_success_at"),
                "live_eligible": live_eligible,
            }
        )

    def sort_key(item: Mapping[str, Any]) -> tuple[Any, ...]:
        due_since = item.get("due_since") or "0000-01-01T00:00:00Z"
        return (int(item["priority"]), due_since, str(item["registry_id"]))

    due_candidates.sort(key=sort_key)
    limit = int(config["max_sources_per_plan"])
    due_sources = due_candidates[:limit]
    overflow = max(0, len(due_candidates) - len(due_sources))
    blocked.sort(key=lambda item: (item["reason"], item["registry_id"]))

    generated_at = format_datetime(observed)
    compact = observed.strftime("%Y%m%dT%H%M%SZ")
    return {
        "schema_version": "1.0.0",
        "plan_id": f"daily-plan-{compact}",
        "generated_at": generated_at,
        "timezone": config.get("timezone", "Asia/Shanghai"),
        "mode": mode,
        "live_enabled": bool(live_enabled),
        "due_sources": due_sources,
        "blocked_sources": blocked,
        "summary": {
            "active_sources": active_count,
            "due_sources": len(due_sources),
            "live_collectable": sum(
                item["action"] == "collect_live" for item in due_sources
            ),
            "manual_review": sum(
                item["action"] == "manual_review" for item in due_sources
            ),
            "blocked_sources": len(blocked),
            "deferred_sources": not_due + overflow,
        },
    }


def failure_fingerprint(
    *,
    stage: str,
    error_type: str,
    message: str,
    source_registry_id: str | None,
) -> str:
    raw = "|".join(
        [stage, error_type, message, source_registry_id or ""]
    ).encode("utf-8")
    return "failure-" + hashlib.sha256(raw).hexdigest()[:32]


def update_source_state(
    state: Mapping[str, Any],
    *,
    registry_id: str,
    observed_at: datetime,
    status: str,
    content_hash: str | None = None,
    failure_fp: str | None = None,
) -> dict[str, Any]:
    """Return a stable state update for one source without mutating input."""
    if status not in {"success", "failure", "skipped"}:
        raise SchedulerError(f"不支持的来源状态：{status}")
    updated = deepcopy(state)
    indexed = {item["registry_id"]: item for item in updated.get("sources", [])}
    item = indexed.get(registry_id)
    if item is None:
        item = _default_state(registry_id)
        updated.setdefault("sources", []).append(item)

    timestamp = format_datetime(observed_at)
    item["last_attempt_at"] = timestamp
    item["last_status"] = status
    if status == "success":
        if not content_hash or not content_hash.startswith("sha256:"):
            raise SchedulerError("成功状态必须提供 sha256 内容哈希")
        item["last_success_at"] = timestamp
        item["last_content_hash"] = content_hash
        item["consecutive_failures"] = 0
        item["last_failure_fingerprint"] = None
    elif status == "failure":
        if not failure_fp or not failure_fp.startswith("failure-"):
            raise SchedulerError("失败状态必须提供 failure 指纹")
        item["consecutive_failures"] = int(item["consecutive_failures"]) + 1
        item["last_failure_fingerprint"] = failure_fp
    else:
        item["last_failure_fingerprint"] = None

    updated["sources"] = sorted(
        updated.get("sources", []), key=lambda value: value["registry_id"]
    )
    updated["updated_at"] = timestamp
    return updated
