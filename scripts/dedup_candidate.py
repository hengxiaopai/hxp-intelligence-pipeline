#!/usr/bin/env python3
"""Evaluate a candidate against the 3/7/30-day history index."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.dedup import apply_decision, evaluate_candidate  # noqa: E402

CANDIDATE_SCHEMA = ROOT / "schemas/candidate.schema.json"
INDEX_SCHEMA = ROOT / "schemas/dedup-index.schema.json"
DECISION_SCHEMA = ROOT / "schemas/dedup-decision.schema.json"


class DedupCliError(Exception):
    """Raised when the deduplication command cannot safely complete."""


def load_object(path: Path, *, allow_missing: bool = False) -> dict[str, Any]:
    if allow_missing and not path.exists():
        return {
            "schema_version": "1.0.0",
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "entries": [],
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DedupCliError(f"文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise DedupCliError(
            f"JSON 解析失败：{path}:{exc.lineno}:{exc.colno} {exc.msg}"
        ) from exc
    if not isinstance(value, dict):
        raise DedupCliError(f"JSON 根节点必须是对象：{path}")
    return value


def validate(value: dict[str, Any], schema_path: Path, label: str) -> None:
    schema = load_object(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(value),
        key=lambda error: [str(part) for part in error.absolute_path],
    )
    if errors:
        lines = [f"{label} 未通过 Schema 校验："]
        for error in errors:
            location = "/" + "/".join(str(part) for part in error.absolute_path)
            lines.append(f"- {location or '/'}: {error.message}")
        raise DedupCliError("\n".join(lines))


def validate_index_semantics(index: dict[str, Any]) -> None:
    entries = index.get("entries", [])
    record_ids = [entry["record_id"] for entry in entries]
    if len(record_ids) != len(set(record_ids)):
        raise DedupCliError("dedup index 的 record_id 不得重复")
    for entry in entries:
        if entry["first_seen"] > entry["last_seen"]:
            raise DedupCliError(f"{entry['record_id']}: first_seen 晚于 last_seen")
        if entry["last_seen"] not in set(entry["occurrence_dates"]):
            raise DedupCliError(
                f"{entry['record_id']}: occurrence_dates 必须包含 last_seen"
            )


def parse_evaluated_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DedupCliError("--evaluated-at 必须是 ISO 8601 时间") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deduplicate one candidate event")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--decision-output", type=Path, required=True)
    parser.add_argument("--updated-index-output", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--title")
    parser.add_argument("--visual-concept")
    parser.add_argument("--new-delta")
    parser.add_argument("--evaluated-at")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.apply and args.updated_index_output is None:
            raise DedupCliError("使用 --apply 时必须提供 --updated-index-output")

        candidate = load_object(args.candidate.resolve())
        index_path = args.index.resolve()
        index = load_object(index_path, allow_missing=True)
        validate(candidate, CANDIDATE_SCHEMA, "candidate")
        validate(index, INDEX_SCHEMA, "dedup index")
        validate_index_semantics(index)

        decision = evaluate_candidate(
            candidate,
            index,
            evaluated_at=parse_evaluated_at(args.evaluated_at),
            proposed_title=args.title,
            visual_concept=args.visual_concept,
            new_delta=args.new_delta,
        )
        validate(decision, DECISION_SCHEMA, "dedup decision")
        write_json(args.decision_output.resolve(), decision)

        print(f"DECISION: {decision['decision']}")
        for reason in decision["reasons"]:
            print(f"- {reason}")

        if args.apply:
            updated_index = apply_decision(
                index,
                candidate,
                decision,
                proposed_title=args.title,
                visual_concept=args.visual_concept,
            )
            validate(updated_index, INDEX_SCHEMA, "updated dedup index")
            validate_index_semantics(updated_index)
            write_json(args.updated_index_output.resolve(), updated_index)
            print(f"INDEX: {args.updated_index_output.resolve()}")
    except (DedupCliError, ValueError) as exc:
        print(f"FAIL\n{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
