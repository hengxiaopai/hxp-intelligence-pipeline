"""Explainable 3/7/30-day deduplication decisions."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import date, datetime, timezone
from typing import Any

from .normalization import (
    dedup_record_id,
    normalize_text,
    text_similarity,
    title_fingerprint,
    topic_fingerprint,
    viewpoint_fingerprint,
    visual_fingerprint,
)

EVENT_WINDOW_DAYS = 3
TOPIC_WINDOW_DAYS = 7
ASSET_WINDOW_DAYS = 30
VIEWPOINT_THRESHOLD = 0.72
TITLE_THRESHOLD = 0.86
VISUAL_THRESHOLD = 0.82


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _days_apart(left: str, right: str) -> int:
    return abs((_parse_date(left) - _parse_date(right)).days)


def _match(
    entry: dict[str, Any],
    match_type: str,
    days: int,
    similarity: float,
    evidence: str,
) -> dict[str, Any]:
    return {
        "record_id": entry["record_id"],
        "match_type": match_type,
        "days_apart": days,
        "similarity": round(similarity, 4),
        "evidence": evidence,
    }


def _has_new_delta(value: str | None) -> bool:
    return bool(value and len(normalize_text(value)) >= 10)


def _decision_id(candidate_id: str, evaluated_at: str, decision: str) -> str:
    raw = f"{candidate_id}|{evaluated_at}|{decision}".encode("utf-8")
    return "decision-" + hashlib.sha256(raw).hexdigest()[:32]


def evaluate_candidate(
    candidate: dict[str, Any],
    index: dict[str, Any],
    *,
    evaluated_at: datetime | None = None,
    proposed_title: str | None = None,
    visual_concept: str | None = None,
    new_delta: str | None = None,
) -> dict[str, Any]:
    """Evaluate one candidate against active history records."""
    observed = evaluated_at or _utc_now()
    evaluated_iso = _iso_datetime(observed)
    candidate_date = candidate["event_date"]
    title = proposed_title or candidate["title_normalized"]
    summary = candidate["summary_raw"]

    topic_fp = topic_fingerprint(
        candidate["primary_category"],
        candidate["canonical_entities"],
        candidate["event_object"],
    )
    view_fp = viewpoint_fingerprint(summary)
    title_fp = title_fingerprint(title)
    visual_fp = visual_fingerprint(visual_concept)

    matches: list[dict[str, Any]] = []
    event_records: list[dict[str, Any]] = []
    topic_records: list[dict[str, Any]] = []
    viewpoint_records: list[dict[str, Any]] = []
    title_warning = False
    visual_warning = False

    for entry in index.get("entries", []):
        if entry.get("status") != "active":
            continue
        days = _days_apart(candidate_date, entry["last_seen"])

        if (
            days <= EVENT_WINDOW_DAYS
            and entry["event_fingerprint"] == candidate["event_fingerprint"]
        ):
            event_records.append(entry)
            matches.append(
                _match(entry, "event", days, 1.0, "事件指纹完全一致且位于 3 天窗口内")
            )

        topic_same = entry["topic_fingerprint"] == topic_fp
        if days <= TOPIC_WINDOW_DAYS and topic_same:
            topic_records.append(entry)
            matches.append(
                _match(entry, "topic", days, 1.0, "主题指纹一致且位于 7 天窗口内")
            )
            similarity = text_similarity(summary, entry["latest_summary"])
            viewpoint_same = (
                entry["viewpoint_fingerprint"] == view_fp
                or similarity >= VIEWPOINT_THRESHOLD
            )
            if viewpoint_same:
                viewpoint_records.append(entry)
                matches.append(
                    _match(
                        entry,
                        "viewpoint",
                        days,
                        similarity,
                        "观点摘要相同或文本相似度达到阈值",
                    )
                )

        if days <= ASSET_WINDOW_DAYS:
            title_similarity = text_similarity(title, entry["latest_title"])
            if entry["title_fingerprint"] == title_fp or title_similarity >= TITLE_THRESHOLD:
                title_warning = True
                matches.append(
                    _match(
                        entry,
                        "title",
                        days,
                        title_similarity,
                        "标题在 30 天窗口内重复或高度相似",
                    )
                )
            if visual_fp and entry.get("visual_fingerprint"):
                visual_similarity = text_similarity(
                    visual_concept or "",
                    entry.get("latest_visual_concept") or "",
                )
                if (
                    entry["visual_fingerprint"] == visual_fp
                    or visual_similarity >= VISUAL_THRESHOLD
                ):
                    visual_warning = True
                    matches.append(
                        _match(
                            entry,
                            "visual",
                            days,
                            visual_similarity,
                            "视觉概念在 30 天窗口内重复或高度相似",
                        )
                    )

    delta_present = _has_new_delta(new_delta)
    reasons: list[str] = []

    if event_records:
        if delta_present:
            decision = "continuation"
            recommended_status = "deduped"
            index_update = "update"
            reasons.append("同一事件位于 3 天窗口内，但提供了可审核的新变化，转为延续跟踪")
        else:
            decision = "reject_duplicate_event"
            recommended_status = "rejected"
            index_update = "none"
            reasons.append("同一事件在最近 3 天已经出现，且没有提供实质 new_delta")
    elif topic_records and viewpoint_records:
        if delta_present:
            decision = "continuation"
            recommended_status = "deduped"
            index_update = "create"
            reasons.append("同主题与观点位于 7 天窗口内，新变化应作为延续跟踪记录")
        else:
            decision = "reject_duplicate_viewpoint"
            recommended_status = "rejected"
            index_update = "none"
            reasons.append("最近 7 天已有相同主题与观点，未发现可证实的新角度")
    else:
        decision = "select_new"
        recommended_status = "pending_review"
        index_update = "create"
        if topic_records:
            reasons.append("主题相近但观点相似度未达到阈值，可作为新角度进入编辑审核")
        else:
            reasons.append("未命中 3 天事件或 7 天主题观点重复规则")

    if title_warning:
        reasons.append("标题在最近 30 天存在重复风险，发布前必须改写")
    if visual_warning:
        reasons.append("视觉概念在最近 30 天存在重复风险，需更换构图或隐喻")

    return {
        "schema_version": "1.0.0",
        "decision_id": _decision_id(candidate["candidate_id"], evaluated_iso, decision),
        "candidate_id": candidate["candidate_id"],
        "evaluated_at": evaluated_iso,
        "windows": {
            "event_days": EVENT_WINDOW_DAYS,
            "topic_days": TOPIC_WINDOW_DAYS,
            "asset_days": ASSET_WINDOW_DAYS,
        },
        "decision": decision,
        "recommended_status": recommended_status,
        "event_match": bool(event_records),
        "topic_match": bool(topic_records),
        "viewpoint_match": bool(viewpoint_records),
        "title_reuse_warning": title_warning,
        "visual_reuse_warning": visual_warning,
        "matched_records": matches,
        "new_delta": new_delta if delta_present else None,
        "reasons": reasons,
        "index_update": index_update,
    }


def _new_entry(
    candidate: dict[str, Any],
    *,
    proposed_title: str,
    visual_concept: str | None,
) -> dict[str, Any]:
    event_fp = candidate["event_fingerprint"]
    event_date = candidate["event_date"]
    summary = candidate["summary_raw"]
    return {
        "record_id": dedup_record_id(event_fp),
        "event_fingerprint": event_fp,
        "topic_fingerprint": topic_fingerprint(
            candidate["primary_category"],
            candidate["canonical_entities"],
            candidate["event_object"],
        ),
        "viewpoint_fingerprint": viewpoint_fingerprint(summary),
        "title_fingerprint": title_fingerprint(proposed_title),
        "visual_fingerprint": visual_fingerprint(visual_concept),
        "canonical_entities": candidate["canonical_entities"],
        "event_action": candidate["event_action"],
        "event_object": candidate["event_object"],
        "primary_category": candidate["primary_category"],
        "first_seen": event_date,
        "last_seen": event_date,
        "occurrence_dates": [event_date],
        "candidate_ids": [candidate["candidate_id"]],
        "item_ids": [],
        "latest_title": proposed_title,
        "latest_summary": summary,
        "latest_visual_concept": visual_concept,
        "status": "active",
    }


def apply_decision(
    index: dict[str, Any],
    candidate: dict[str, Any],
    decision: dict[str, Any],
    *,
    proposed_title: str | None = None,
    visual_concept: str | None = None,
) -> dict[str, Any]:
    """Apply an accepted decision to a copy of the history index."""
    updated = deepcopy(index)
    updated["updated_at"] = decision["evaluated_at"]
    action = decision["index_update"]
    if action == "none":
        return updated

    title = proposed_title or candidate["title_normalized"]
    if action == "create":
        record = _new_entry(
            candidate,
            proposed_title=title,
            visual_concept=visual_concept,
        )
        existing_ids = {entry["record_id"] for entry in updated.get("entries", [])}
        if record["record_id"] not in existing_ids:
            updated.setdefault("entries", []).append(record)
        return updated

    event_matches = [
        match
        for match in decision["matched_records"]
        if match["match_type"] == "event"
    ]
    if not event_matches:
        raise ValueError("index_update=update 但缺少 event 匹配记录")
    record_id = event_matches[0]["record_id"]
    for entry in updated.get("entries", []):
        if entry["record_id"] != record_id:
            continue
        event_date = candidate["event_date"]
        entry["last_seen"] = max(entry["last_seen"], event_date)
        entry["occurrence_dates"] = sorted(
            set([*entry["occurrence_dates"], event_date])
        )
        entry["candidate_ids"] = sorted(
            set([*entry["candidate_ids"], candidate["candidate_id"]])
        )
        entry["viewpoint_fingerprint"] = viewpoint_fingerprint(candidate["summary_raw"])
        entry["title_fingerprint"] = title_fingerprint(title)
        entry["visual_fingerprint"] = visual_fingerprint(visual_concept)
        entry["latest_title"] = title
        entry["latest_summary"] = candidate["summary_raw"]
        entry["latest_visual_concept"] = visual_concept
        return updated
    raise ValueError(f"去重索引中找不到记录：{record_id}")
