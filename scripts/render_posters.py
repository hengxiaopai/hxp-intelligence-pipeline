#!/usr/bin/env python3
"""Render one visual queue into SVG/PNG posters and a validated manifest."""

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

from visual.pipeline import VisualPipelineError, render_visual_queue, write_json  # noqa: E402
from visual.queue import load_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--theme", type=Path, default=ROOT / "config/visual-theme.json")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--placeholder", type=Path)
    parser.add_argument("--svg-only", action="store_true")
    parser.add_argument(
        "--allow-failed",
        action="store_true",
        help="write the manifest but return success even when an asset failed",
    )
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
        queue = load_json(args.queue)
        theme = load_json(args.theme)
        manifest = render_visual_queue(
            queue=queue,
            theme=theme,
            output_dir=args.output_dir,
            placeholder_path=args.placeholder,
            rasterize=not args.svg_only,
        )
        errors = schema_errors(ROOT / "schemas/visual-manifest.schema.json", manifest)
        if errors:
            raise VisualPipelineError(
                "视觉Manifest Schema校验失败：\n- " + "\n- ".join(errors)
            )
        write_json(args.manifest, manifest)
    except (VisualPipelineError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    summary = manifest["summary"]
    print(
        "PASS visual render: "
        f"total={summary['total']} passed={summary['passed']} "
        f"failed={summary['failed']} png={summary['png_assets']}"
    )
    if summary["failed"] and not args.allow_failed:
        for asset in manifest["assets"]:
            if asset["status"] == "failed":
                print(
                    f"FAILED {asset['job_id']}: {'; '.join(asset['errors'])}",
                    file=sys.stderr,
                )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
