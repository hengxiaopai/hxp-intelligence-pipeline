#!/usr/bin/env python3
"""Validate human visual decisions and apply review states to a request queue."""

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
from visual.review import (  # noqa: E402
    VisualReviewError,
    apply_review_batch,
    build_review_batch,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--review-output", type=Path, required=True)
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
        decisions = load_json(args.decisions)
        reviewer = decisions.get("reviewer", {})
        review_batch = build_review_batch(
            request_queue=request_queue,
            decisions=list(decisions.get("decisions", [])),
            reviewer_type=str(reviewer.get("type", "")),
            reviewer_identifier=str(reviewer.get("identifier", "")),
            reviewed_at=str(decisions.get("reviewed_at", "")),
        )
        errors = schema_errors(ROOT / "schemas/visual-review.schema.json", review_batch)
        if errors:
            raise VisualReviewError(
                "视觉审核Schema校验失败：\n- " + "\n- ".join(errors)
            )
        updated_requests = apply_review_batch(
            request_queue=request_queue,
            review_batch=review_batch,
        )
        request_errors = schema_errors(
            ROOT / "schemas/visual-request.schema.json", updated_requests
        )
        if request_errors:
            raise VisualReviewError(
                "审核后的请求队列Schema校验失败：\n- "
                + "\n- ".join(request_errors)
            )
        write_json(args.review_output, review_batch)
        write_json(args.requests_output, updated_requests)
    except (VisualReviewError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    summary = review_batch["summary"]
    print(
        "PASS visual review: "
        f"approved={summary['approved']} rejected={summary['rejected']} "
        f"needs_changes={summary['needs_changes']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
