#!/usr/bin/env python3
"""Generate an offline official-connector qualification report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from publishing.qualification import QualificationError, evaluate_qualifications  # noqa: E402
from visual.pipeline import write_json  # noqa: E402
from visual.queue import load_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "config/official-connectors.json")
    parser.add_argument("--generated-at", required=True)
    parser.add_argument("--report-slug", default="audit")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def schema_errors(payload: Any) -> list[str]:
    validator = Draft202012Validator(
        load_json(ROOT / "schemas/connector-qualification.schema.json"),
        format_checker=FormatChecker(),
    )
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(
            validator.iter_errors(payload),
            key=lambda error: [str(part) for part in error.absolute_path],
        )
    ]


def main() -> int:
    args = parse_args()
    try:
        report = evaluate_qualifications(
            config=load_json(args.config),
            facts=load_json(args.facts),
            generated_at=args.generated_at,
            report_slug=args.report_slug,
        )
        errors = schema_errors(report)
        if errors:
            raise QualificationError("资格报告Schema校验失败：\n- " + "\n- ".join(errors))
        write_json(args.output, report)
    except (QualificationError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        "PASS official qualifications: "
        f"unknown={report['summary']['unknown']} eligible={report['summary']['eligible']} "
        f"blocked={report['summary']['blocked']} simulated={report['summary']['simulated']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
