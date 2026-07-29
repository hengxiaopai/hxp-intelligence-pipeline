#!/usr/bin/env python3
"""Build five validated platform draft packages from briefing and export assets."""

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

from publishing.package_builder import (  # noqa: E402
    ContentPackageError,
    build_content_package_batch,
    load_sources,
)
from visual.pipeline import write_json  # noqa: E402
from visual.queue import load_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--export-manifest", type=Path, required=True)
    parser.add_argument("--profiles", type=Path, default=ROOT / "config/platform-profiles.json")
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
        batch = build_content_package_batch(
            briefing=load_json(args.run_dir / "briefing.json"),
            export_manifest=load_json(args.export_manifest),
            sources=load_sources(args.run_dir / "sources"),
            profiles=load_json(args.profiles),
        )
        errors = schema_errors(ROOT / "schemas/content-package.schema.json", batch)
        if errors:
            raise ContentPackageError("内容包Schema校验失败：\n- " + "\n- ".join(errors))
        write_json(args.output, batch)
    except (ContentPackageError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        "PASS content packages: "
        f"validated={batch['summary']['validated']} blocked={batch['summary']['blocked']}"
    )
    return 1 if batch["summary"]["blocked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
