"""Atomically prepare dedup history and source watermark updates.

History advancement is deliberately separate from daily generation. Only a fully
validated and human-approved run may update production state.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from .dedup import apply_decision, evaluate_candidate
from .scheduler import parse_datetime, update_source_state


class HistoryCommitError(ValueError):
    """Raised when a run is not eligible to advance production history."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HistoryCommitError(f"文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise HistoryCommitError(
            f"JSON 无效：{path}:{exc.lineno}:{exc.colno}"
        ) from exc


def assert_run_approved(run_record: Mapping[str, Any]) -> None:
    if run_record.get("status") != "validated":
        raise HistoryCommitError("只有 status=validated 的运行可以提交历史")
    if run_record.get("review_status") != "approved":
        raise HistoryCommitError("只有人工审核 approved 的运行可以提交历史")
    if run_record.get("publication_allowed") is not True:
        raise HistoryCommitError("publication_allowed=false，禁止提交正式历史")
    validations = run_record.get("validations", {})
    failed = sorted(key for key, value in validations.items() if value is not True)
    if failed:
        raise HistoryCommitError(f"运行仍有未通过验证：{failed}")


def _selected_items(briefing: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        *briefing.get("new_items", []),
        *briefing.get("continuation_items", []),
    ]


def _candidate_by_event(pool: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for entry in pool.get("entries", []):
        candidate = entry["candidate"]
        fingerprint = candidate["event_fingerprint"]
        if fingerprint in result:
            raise HistoryCommitError(f"候选事件指纹重复：{fingerprint}")
        result[fingerprint] = entry
    return result


def _record_with_item(index: Mapping[str, Any], item_id: str) -> Mapping[str, Any] | None:
    for record in index.get("entries", []):
        if item_id in record.get("item_ids", []):
            return record
    return None


def _attach_item_id(
    index: dict[str, Any],
    *,
    candidate: Mapping[str, Any],
    item_id: str,
) -> None:
    matches = [
        entry
        for entry in index.get("entries", [])
        if entry.get("event_fingerprint") == candidate["event_fingerprint"]
        or candidate["candidate_id"] in entry.get("candidate_ids", [])
    ]
    if len(matches) != 1:
        raise HistoryCommitError(
            f"无法唯一定位去重记录：{candidate['candidate_id']}，匹配数={len(matches)}"
        )
    record = matches[0]
    record["item_ids"] = sorted(set([*record.get("item_ids", []), item_id]))
    record["candidate_ids"] = sorted(
        set([*record.get("candidate_ids", []), candidate["candidate_id"]])
    )


def _combined_registry_hash(entries: list[Mapping[str, Any]]) -> str:
    hashes = sorted(
        {
            str(entry["candidate"]["ingestion"]["content_hash"])
            for entry in entries
        }
    )
    payload = "\n".join(hashes).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def prepare_history_commit(
    *,
    run_dir: Path,
    source_state: Mapping[str, Any],
    dedup_index: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Return updated state, updated dedup index, and an audit summary."""
    run_record = load_json(run_dir / "run.json")
    assert_run_approved(run_record)
    pool = load_json(run_dir / "candidate-pool.json")
    briefing = load_json(run_dir / "briefing.json")

    if pool.get("date") != run_record.get("date"):
        raise HistoryCommitError("candidate-pool 日期与 run.json 不一致")
    if briefing.get("date") != run_record.get("date"):
        raise HistoryCommitError("briefing 日期与 run.json 不一致")

    by_event = _candidate_by_event(pool)
    updated_index = deepcopy(dedup_index)
    selected_entries: list[Mapping[str, Any]] = []
    committed_items: list[str] = []
    skipped_items: list[str] = []
    evaluated_at = parse_datetime(str(run_record["generated_at"]))

    for item in _selected_items(briefing):
        item_id = str(item["item_id"])
        existing = _record_with_item(updated_index, item_id)
        if existing is not None:
            skipped_items.append(item_id)
            fingerprint = item["event_fingerprint"]
            if fingerprint in by_event:
                selected_entries.append(by_event[fingerprint])
            continue

        fingerprint = item["event_fingerprint"]
        entry = by_event.get(fingerprint)
        if entry is None:
            raise HistoryCommitError(f"正式条目找不到候选事件：{item_id}")
        candidate = entry["candidate"]
        selected_entries.append(entry)
        visual_concept = item.get("visual_brief", {}).get("concept")
        continuation = item.get("continuation") or {}
        new_delta = continuation.get("new_delta")
        decision = evaluate_candidate(
            candidate,
            updated_index,
            evaluated_at=evaluated_at,
            proposed_title=item["title"],
            visual_concept=visual_concept,
            new_delta=new_delta,
        )
        if decision["decision"] not in {"select_new", "continuation"}:
            raise HistoryCommitError(
                f"已批准条目无法通过正式历史去重：{item_id} -> "
                f"{decision['decision']}"
            )
        updated_index = apply_decision(
            updated_index,
            candidate,
            decision,
            proposed_title=item["title"],
            visual_concept=visual_concept,
        )
        _attach_item_id(updated_index, candidate=candidate, item_id=item_id)
        committed_items.append(item_id)

    updated_index["entries"] = sorted(
        updated_index.get("entries", []), key=lambda value: value["record_id"]
    )
    updated_index["updated_at"] = run_record["generated_at"]

    registry_entries: dict[str, list[Mapping[str, Any]]] = {}
    for entry in selected_entries:
        registry_id = entry["candidate"]["ingestion"]["source_registry_id"]
        registry_entries.setdefault(registry_id, []).append(entry)

    updated_state = deepcopy(source_state)
    for registry_id in sorted(registry_entries):
        updated_state = update_source_state(
            updated_state,
            registry_id=registry_id,
            observed_at=evaluated_at,
            status="success",
            content_hash=_combined_registry_hash(registry_entries[registry_id]),
        )

    summary = {
        "run_id": run_record["run_id"],
        "committed_at": run_record["generated_at"],
        "committed_item_ids": committed_items,
        "already_committed_item_ids": skipped_items,
        "updated_registry_ids": sorted(registry_entries),
        "dedup_entry_count": len(updated_index.get("entries", [])),
        "idempotent": not committed_items and bool(skipped_items),
    }
    return updated_state, updated_index, summary
