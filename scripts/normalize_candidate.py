#!/usr/bin/env python3
"""Create one candidate event from a raw snapshot item plus explicit hints.

The command does not infer event semantics. Entities, action, object, category,
and information type are explicit inputs so the normalizer cannot fabricate a
story from a headline.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.normalization import (  # noqa: E402
    canonicalize_entities,
    event_fingerprint,
    load_alias_map,
)

DEFAULT_ALIASES = ROOT / "config/entity-aliases.json"
DEFAULT_SCHEMA = ROOT / "schemas/candidate.schema.json"


class NormalizeError(Exception):
    """Raised when candidate normalization cannot be completed safely."""


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise NormalizeError(f"文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise NormalizeError(
            f"JSON 解析失败：{path}:{exc.lineno}:{exc.colno} {exc.msg}"
        ) from exc
    if not isinstance(value, dict):
        raise NormalizeError(f"JSON 根节点必须是对象：{path}")
    return value


def display_normalize(value: str, limit: int) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())[:limit]


def parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise NormalizeError(f"无效时间：{value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def freshness_score(published_at: str | None, observed_at: str) -> int:
    if not published_at:
        return 55
    published = parse_datetime(published_at)
    observed = parse_datetime(observed_at)
    hours = max(0.0, (observed - published).total_seconds() / 3600)
    if hours <= 24:
        return 100
    if hours <= 48:
        return 90
    if hours <= 72:
        return 80
    if hours <= 168:
        return 65
    return 40


def confidence(source: dict[str, Any]) -> tuple[str, int]:
    authority = source["authority_level"]
    verification = source["verification_status"]
    if verification == "unverified":
        return "low", 30
    if authority == "tier_1_official" and verification in {"verified", "cross_checked"}:
        return "high", 98
    if authority == "tier_2_reliable_media" and verification in {"verified", "cross_checked"}:
        return "medium_high", 80
    return "observe", 50


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def validate_candidate(candidate: dict[str, Any], schema_path: Path) -> None:
    schema = load_object(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(candidate),
        key=lambda error: [str(part) for part in error.absolute_path],
    )
    if errors:
        lines = ["候选事件未通过 Schema 校验："]
        for error in errors:
            location = "/" + "/".join(str(part) for part in error.absolute_path)
            lines.append(f"- {location or '/'}: {error.message}")
        raise NormalizeError("\n".join(lines))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize one snapshot item")
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--item-index", type=int, default=0)
    parser.add_argument("--sequence", type=int, default=1)
    parser.add_argument("--entity", action="append", required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--object", dest="event_object", required=True)
    parser.add_argument("--event-date")
    parser.add_argument("--primary-category", required=True)
    parser.add_argument("--information-type", action="append", required=True)
    parser.add_argument("--risk-flag", action="append", default=[])
    parser.add_argument("--relevance-score", type=int, default=75)
    parser.add_argument("--aliases", type=Path, default=DEFAULT_ALIASES)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.sequence < 1 or args.sequence > 999:
            raise NormalizeError("--sequence 必须在 1–999 之间")
        if args.relevance_score < 0 or args.relevance_score > 100:
            raise NormalizeError("--relevance-score 必须在 0–100 之间")

        snapshot = load_object(args.snapshot.resolve())
        source = load_object(args.source.resolve())
        items = snapshot.get("items", [])
        if args.item_index < 0 or args.item_index >= len(items):
            raise NormalizeError(
                f"--item-index 超出范围：{args.item_index}，快照共有 {len(items)} 条"
            )
        item = items[args.item_index]

        alias_map = load_alias_map(args.aliases.resolve())
        entities = canonicalize_entities(args.entity, alias_map)
        if not entities:
            raise NormalizeError("规范化后没有有效实体")

        published_at = item.get("published_at")
        event_date = args.event_date or (
            published_at[:10] if isinstance(published_at, str) else None
        )
        if not event_date:
            raise NormalizeError("来源没有发布时间，必须显式提供 --event-date")
        try:
            datetime.strptime(event_date, "%Y-%m-%d")
        except ValueError as exc:
            raise NormalizeError("--event-date 必须为 YYYY-MM-DD") from exc

        title_raw = str(item["title"])
        title_normalized = display_normalize(title_raw, 120)
        summary = display_normalize(
            str(item.get("summary") or f"{title_raw}。来源未提供摘要，等待编辑复核。"),
            800,
        )
        level, authority_score = confidence(source)
        risk_flags = unique(args.risk_flag or ["none"])
        if source["authority_level"] == "tier_3_signal_only":
            risk_flags = [flag for flag in risk_flags if flag != "none"]
            risk_flags.append("community_content")
        risk_flags = unique(risk_flags)

        source_urls = unique([str(item["url"]), str(source["url"])])
        event_fp = event_fingerprint(
            entities,
            args.action,
            args.event_object,
            event_date,
        )
        candidate_id = f"candidate-{event_date.replace('-', '')}-{args.sequence:03d}"
        observed_at = str(snapshot["retrieved_at"])

        candidate = {
            "schema_version": "1.0.0",
            "candidate_id": candidate_id,
            "observed_at": observed_at,
            "title_raw": title_raw[:220],
            "title_normalized": title_normalized,
            "canonical_entities": entities,
            "event_action": display_normalize(args.action, 80),
            "event_object": display_normalize(args.event_object, 120),
            "event_date": event_date,
            "primary_category": args.primary_category,
            "information_types": unique(args.information_type),
            "summary_raw": summary,
            "source_ids": [source["source_id"]],
            "source_urls": source_urls,
            "evidence_claims": [
                {
                    "claim": summary[:240],
                    "source_id": source["source_id"],
                    "support_level": "direct",
                    "evidence_text": source["evidence_summary"][:500],
                }
            ],
            "authority_score": authority_score,
            "freshness_score": freshness_score(published_at, observed_at),
            "relevance_score": args.relevance_score,
            "preliminary_confidence": level,
            "event_fingerprint": event_fp,
            "dedup_keys": {
                "entities": entities,
                "action": display_normalize(args.action, 80),
                "object": display_normalize(args.event_object, 120),
                "date_bucket": event_date,
            },
            "risk_flags": risk_flags,
            "ingestion": {
                "source_registry_id": snapshot["source_registry_id"],
                "collection_method": snapshot["collection_method"],
                "retrieved_at": observed_at,
                "content_hash": snapshot["content_hash"],
                "parser_version": snapshot["parser_version"],
                "raw_snapshot_path": args.snapshot.resolve().as_posix(),
            },
            "status": "pending_review",
            "rejection_reason": None,
        }
        validate_candidate(candidate, args.schema.resolve())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(candidate, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"PASS candidate: {args.output}")
        print(f"FINGERPRINT: {event_fp}")
    except (NormalizeError, ValueError) as exc:
        print(f"FAIL\n{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
