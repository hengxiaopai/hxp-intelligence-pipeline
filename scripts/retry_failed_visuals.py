#!/usr/bin/env python3
"""Create and apply targeted retry requests from a human visual review batch."""

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

from visual.pipeline import write_json  # noqa: E402
from visual.queue import load_json  # noqa: E402
from visual.retry_policy import (  # noqa: E402
    VisualRetryError,
    apply_retry_plan,
    build_retry_plan,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--generated-at")
    parser.add_argument("--plan-output", type=Path, required=True)
    parser.add_argument("--requests-output", type=Path, required=True)
    return parser.parse_args()


def schema_errors(schema_path: Path, value: Any) -> list[str]:
    schema = load_json(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(
            validator.iter_errors(value),
            key=lambda error: [str(part) for part in error.absolute_path],
        )
    ]


def main() -> int:
    args = parse_args()
    try:
        request_queue = load_json(args.requests)
        review_batch = load_json(args.review)
        retry_plan, scheduled = build_retry_plan(
            request_queue=request_queue,
            review_batch=review_batch,
            generated_at=args.generated_at,
        )
        plan_errors = schema_errors(
            ROOT / "schemas/visual-retry.schema.json", retry_plan
        )
        if plan_errors:
            raise VisualRetryError(
                "视觉重试计划Schema校验失败：\n- " + "\n- ".join(plan_errors)
            )
        updated_requests = apply_retry_plan(
            request_queue=request_queue,
            retry_plan=retry_plan,
            scheduled_requests=scheduled,
        )
        request_errors = schema_errors(
            ROOT / "schemas/visual-request.schema.json", updated_requests
        )
        if request_errors:
            raise VisualRetryError(
                "重试后的请求队列Schema校验失败：\n- "
                + "\n- ".join(request_errors)
            )
        write_json(args.plan_output, retry_plan)
        write_json(args.requests_output, updated_requests)
    except (VisualRetryError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    summary = retry_plan["summary"]
    print(
        "PASS visual retry: "
        f"eligible={summary['eligible']} scheduled={summary['scheduled']} "
        f"exhausted={summary['exhausted']} "
        f"editorial_blocked={summary['editorial_blocked']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
