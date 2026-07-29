#!/usr/bin/env python3
"""Render five platform previews locally; never perform an external write."""

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

from publishing.dry_run import PublicationDryRunError, build_dry_run_result  # noqa: E402
from visual.pipeline import write_json  # noqa: E402
from visual.queue import load_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packages", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--executed-at", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
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
        approval = load_json(args.approval) if args.approval else None
        result = build_dry_run_result(
            package_batch=load_json(args.packages),
            plan=load_json(args.plan),
            approval=approval,
            output_dir=args.output_dir,
            executed_at=args.executed_at,
        )
        errors = schema_errors(ROOT / "schemas/publication-result.schema.json", result)
        if errors:
            raise PublicationDryRunError("预览结果Schema校验失败：\n- " + "\n- ".join(errors))
        write_json(args.result, result)
    except (PublicationDryRunError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        "PASS publication preview: "
        f"previewed={result['summary']['previewed']} blocked={result['summary']['blocked']} "
        f"failed={result['summary']['failed']} external_write={result['external_write_performed']}"
    )
    return 1 if result["summary"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
