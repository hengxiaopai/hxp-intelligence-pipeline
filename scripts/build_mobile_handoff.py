#!/usr/bin/env python3
"""Build a verified phone-transfer bundle for Xiaohongshu, Douyin and Zhihu."""

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

from publishing.mobile_handoff import MobileHandoffError, build_mobile_handoff  # noqa: E402
from visual.pipeline import write_json  # noqa: E402
from visual.queue import load_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff-manifest", type=Path, required=True)
    parser.add_argument("--handoff-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--generated-at", required=True)
    return parser.parse_args()


def schema_errors(schema_path: Path, payload: Any) -> list[str]:
    validator = Draft202012Validator(load_json(schema_path), format_checker=FormatChecker())
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
        manifest = build_mobile_handoff(
            handoff_manifest=load_json(args.handoff_manifest),
            handoff_root=args.handoff_root,
            output_dir=args.output_dir,
            generated_at=args.generated_at,
        )
        errors = schema_errors(ROOT / "schemas/mobile-handoff.schema.json", manifest)
        if errors:
            raise MobileHandoffError(
                "Mobile Handoff Schema校验失败：\n- " + "\n- ".join(errors)
            )
        write_json(args.manifest, manifest)
    except (MobileHandoffError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        "PASS mobile handoff: "
        f"ready={manifest['summary']['ready']} assets={manifest['summary']['assets']} "
        f"external_write={manifest['external_write_performed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
