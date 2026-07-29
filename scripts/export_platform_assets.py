#!/usr/bin/env python3
"""Export approved HXP visual assets into independent platform templates."""

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

from visual.export_polish import ExportPolishError, export_platform_assets  # noqa: E402
from visual.multiformat import MultiFormatExportError  # noqa: E402
from visual.pipeline import write_json  # noqa: E402
from visual.queue import load_json  # noqa: E402
from visual.rasterizer import RasterizationError, assert_cjk_font_available  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--visual-queue", type=Path, required=True)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--presets", type=Path, default=ROOT / "config/export-presets.json")
    parser.add_argument("--theme", type=Path, default=ROOT / "config/visual-theme.json")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--allow-failed",
        action="store_true",
        help="write the manifest but return success when a template reports text overflow",
    )
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
        requests = load_json(args.requests)
        review = load_json(args.review)
        presets = load_json(args.presets)
        theme = load_json(args.theme)
        typography = theme.get("typography", {})
        candidates = [str(typography.get("primary_family", ""))]
        candidates.extend(
            value.strip()
            for value in str(typography.get("fallback_stack", "")).split(",")
        )
        assert_cjk_font_available(candidates)
        manifest = export_platform_assets(
            visual_queue=visual_queue,
            request_queue=requests,
            review_batch=review,
            presets_config=presets,
            theme=theme,
            output_dir=args.output_dir,
        )
        errors = schema_errors(ROOT / "schemas/export-manifest.schema.json", manifest)
        if errors:
            raise MultiFormatExportError(
                "多平台Manifest Schema校验失败：\n- " + "\n- ".join(errors)
            )
        write_json(args.manifest, manifest)
    except (
        ExportPolishError,
        MultiFormatExportError,
        RasterizationError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    summary = manifest["summary"]
    print(
        "PASS platform export: "
        f"total={summary['total']} passed={summary['passed']} failed={summary['failed']}"
    )
    if summary["failed"] and not args.allow_failed:
        for export in manifest["exports"]:
            if export["status"] == "failed":
                print(
                    f"FAILED {export['export_id']}: {'; '.join(export['errors'])}",
                    file=sys.stderr,
                )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
