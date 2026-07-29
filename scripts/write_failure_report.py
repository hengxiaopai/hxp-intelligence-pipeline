#!/usr/bin/env python3
"""Write a secret-safe pipeline failure report with cooldown-aware issue eligibility."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.failure_reporting import build_failure_report  # noqa: E402
from pipeline.scheduler import parse_datetime  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        required=True,
        choices=[
            "planning",
            "collection",
            "normalization",
            "dedup",
            "editorial_scoring",
            "briefing_assembly",
            "validation",
            "history_commit",
            "visual",
            "publication",
        ],
    )
    parser.add_argument("--error-type", required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--occurred-at", help="ISO 8601；省略时使用当前UTC")
    parser.add_argument("--run-id")
    parser.add_argument("--source-registry-id")
    parser.add_argument("--non-retryable", action="store_true")
    parser.add_argument("--issue-enabled", action="store_true")
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config/schedule.json",
    )
    parser.add_argument(
        "--history-dir",
        type=Path,
        default=ROOT / "data/failures",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def prior_reports(directory: Path) -> list[dict]:
    reports: list[dict] = []
    if not directory.exists():
        return reports
    for path in sorted(directory.rglob("*.json")):
        try:
            value = load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if value.get("schema_version") == "1.0.0" and value.get("fingerprint"):
            reports.append(value)
    return reports


def validate(report: dict) -> None:
    schema = load_json(ROOT / "schemas/failure-report.schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(report),
        key=lambda error: [str(part) for part in error.absolute_path],
    )
    if errors:
        raise ValueError("；".join(error.message for error in errors))


def atomic_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    args = parse_args()
    observed = (
        parse_datetime(args.occurred_at)
        if args.occurred_at
        else datetime.now(timezone.utc)
    )
    config = load_json(args.config)
    report = build_failure_report(
        occurred_at=observed,
        stage=args.stage,
        error_type=args.error_type,
        message=args.message,
        config=config,
        prior_reports=prior_reports(args.history_dir),
        run_id=args.run_id,
        source_registry_id=args.source_registry_id,
        retryable=not args.non_retryable,
        issue_enabled=args.issue_enabled,
    )
    validate(report)
    output = args.output
    if output is None:
        date_dir = args.history_dir / report["occurred_at"][:10]
        output = date_dir / f"{report['failure_id']}-{report['occurrence_count']:03d}.json"
    atomic_write(output, report)
    print(
        f"PASS failure report: {output} "
        f"(count={report['occurrence_count']}, "
        f"issue_eligible={str(report['issue_eligible']).lower()})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
