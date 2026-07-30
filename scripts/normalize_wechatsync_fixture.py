#!/usr/bin/env python3
"""Normalize Wechatsync fixture responses without launching the bridge or browser."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from publishing.bridges import (  # noqa: E402
    BrowserBridgeError,
    normalize_bridge_result,
    normalize_health_snapshot,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["health", "result"], required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--at", required=True)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--extension-connected", choices=["true", "false", "unknown"], default="unknown")
    parser.add_argument("--credential-present", choices=["true", "false", "unknown"], default="unknown")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def tri_state(value: str) -> bool | None:
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def validate(schema_name: str, value: object) -> None:
    schema = json.loads((ROOT / "schemas" / schema_name).read_text(encoding="utf-8"))
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value)
    )
    if errors:
        raise BrowserBridgeError(
            f"{schema_name}校验失败：" + "; ".join(error.message for error in errors)
        )


def main() -> int:
    args = parse_args()
    try:
        raw = json.loads(args.raw.read_text(encoding="utf-8"))
        if args.kind == "health":
            raw_platforms = raw.get("platforms", raw)
            if not isinstance(raw_platforms, list):
                raise BrowserBridgeError("健康Fixture必须是平台数组或包含platforms数组")
            value = normalize_health_snapshot(
                raw_platforms=raw_platforms,
                checked_at=args.at,
                extension_connected=tri_state(args.extension_connected),
                credential_present=tri_state(args.credential_present),
                mode="fixture",
            )
            validate("browser-bridge-health.schema.json", value)
        else:
            if args.request is None:
                raise BrowserBridgeError("结果Fixture必须提供 --request")
            request = json.loads(args.request.read_text(encoding="utf-8"))
            value = normalize_bridge_result(
                request=request,
                raw_result=raw,
                completed_at=args.at,
                mode="fixture",
            )
            validate("browser-bridge-result.schema.json", value)

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (BrowserBridgeError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"PASS Wechatsync {args.kind} fixture: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
