#!/usr/bin/env python3
"""Apply explicit human publication decisions while keeping writes disabled."""

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

from publishing.approval import (  # noqa: E402
    PublicationApprovalError,
    apply_publication_approval,
    build_publication_approval,
)
from visual.pipeline import write_json  # noqa: E402
from visual.queue import load_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--approval-output", type=Path, required=True)
    parser.add_argument("--plan-output", type=Path, required=True)
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
        plan = load_json(args.plan)
        payload = load_json(args.decisions)
        approver = payload.get("approver", {})
        approval = build_publication_approval(
            plan=plan,
            decisions=payload.get("decisions", []),
            approver_identifier=str(approver.get("identifier", "")),
            approved_at=str(payload.get("approved_at", "")),
        )
        updated_plan = apply_publication_approval(plan=plan, approval=approval)
        errors = schema_errors(ROOT / "schemas/publication-approval.schema.json", approval)
        errors.extend(schema_errors(ROOT / "schemas/publication-plan.schema.json", updated_plan))
        if errors:
            raise PublicationApprovalError("发布审核Schema校验失败：\n- " + "\n- ".join(errors))
        write_json(args.approval_output, approval)
        write_json(args.plan_output, updated_plan)
    except (PublicationApprovalError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        "PASS publication approval: "
        f"approved={approval['summary']['approved']} rejected={approval['summary']['rejected']} "
        f"write_actions_enabled={updated_plan['write_actions_enabled']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
