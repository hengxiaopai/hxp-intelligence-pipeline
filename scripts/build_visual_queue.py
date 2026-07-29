#!/usr/bin/env python3
"""Build and validate a fixed-template poster queue from an approved daily run."""

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
from visual.queue import VisualQueueError, build_visual_queue, load_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--logo", type=Path, required=True)
    parser.add_argument("--theme", type=Path, default=ROOT / "config/visual-theme.json")
    parser.add_argument("--visual-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-placeholder", action="store_true")
    return parser.parse_args()


def schema_errors(schema_path: Path, value: Any) -> list[str]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(value),
        key=lambda error: [str(part) for part in error.absolute_path],
    )
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in errors
    ]


def main() -> int:
    args = parse_args()
    try:
        theme = load_json(args.theme)
        queue = build_visual_queue(
            run_dir=args.run_dir,
            logo_path=args.logo,
            theme=theme,
            visual_dir=args.visual_dir,
            allow_placeholder=args.allow_placeholder,
        )
        errors = schema_errors(ROOT / "schemas/visual-queue.schema.json", queue)
        if errors:
            raise VisualQueueError("视觉队列Schema校验失败：\n- " + "\n- ".join(errors))
        write_json(args.output, queue)
    except (VisualQueueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"PASS visual queue: {args.output}")
    print(f"jobs={len(queue['jobs'])} preview_only={queue['preview_only']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
