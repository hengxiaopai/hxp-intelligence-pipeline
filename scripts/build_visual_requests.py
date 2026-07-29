#!/usr/bin/env python3
"""Build stable no-text AI visual requests from a Phase 4.1 visual queue."""

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
from visual.request_queue import (  # noqa: E402
    VisualRequestError,
    build_visual_request_queue,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--visual-queue", type=Path, required=True)
    parser.add_argument(
        "--providers",
        type=Path,
        default=ROOT / "config/visual-providers.json",
    )
    parser.add_argument(
        "--provider",
        choices=["manual_chatgpt", "fixture"],
        default=None,
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def schema_errors(schema_path: Path, value: Any) -> list[str]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
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
        visual_queue = load_json(args.visual_queue)
        providers = load_json(args.providers)
        request_queue = build_visual_request_queue(
            visual_queue=visual_queue,
            provider_config=providers,
            provider_id=args.provider,
        )
        errors = schema_errors(
            ROOT / "schemas/visual-request.schema.json",
            request_queue,
        )
        if errors:
            raise VisualRequestError(
                "主视觉请求Schema校验失败：\n- " + "\n- ".join(errors)
            )
        write_json(args.output, request_queue)
    except (VisualRequestError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(
        f"PASS visual requests: {args.output} "
        f"requests={len(request_queue['requests'])} "
        f"provider={request_queue['provider_policy']['default_provider']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
