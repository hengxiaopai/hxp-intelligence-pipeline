#!/usr/bin/env python3
"""Build a deterministic no-write publication plan from content packages."""

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

from publishing.plan import PublicationPlanError, build_publication_plan  # noqa: E402
from visual.pipeline import write_json  # noqa: E402
from visual.queue import load_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packages", type=Path, required=True)
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def schema_errors(schema_path: Path, payload: Any) -> list[str]:
    schema = load_json(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
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
        plan = build_publication_plan(
            package_batch=load_json(args.packages),
            created_at=args.created_at,
        )
        errors = schema_errors(ROOT / "schemas/publication-plan.schema.json", plan)
        if errors:
            raise PublicationPlanError("发布计划Schema校验失败：\n- " + "\n- ".join(errors))
        write_json(args.output, plan)
    except (PublicationPlanError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        "PASS publication plan: "
        f"pending={plan['summary']['pending']} blocked={plan['summary']['blocked']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
