#!/usr/bin/env python3
"""Validate and display disabled-by-default local browser bridge capabilities."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from publishing.bridges import BrowserBridgeError, load_bridge_registry  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        type=Path,
        default=ROOT / "config/local-browser-bridges.json",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        registry = load_bridge_registry(args.registry)
        schema = json.loads(
            (ROOT / "schemas/browser-bridge-capability.schema.json").read_text(
                encoding="utf-8"
            )
        )
        errors = list(
            Draft202012Validator(
                schema, format_checker=FormatChecker()
            ).iter_errors(registry)
        )
        if errors:
            raise BrowserBridgeError(
                "桥接注册表Schema校验失败："
                + "; ".join(error.message for error in errors)
            )
    except (BrowserBridgeError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(registry, ensure_ascii=False, indent=2))
    else:
        print("PASS local browser bridge registry")
        print(
            f"real_calls={registry['real_bridge_calls_enabled']} "
            f"loopback_only={registry['loopback_only']} "
            f"remote_allowed={registry['remote_bridge_allowed']}"
        )
        for bridge in registry["bridges"]:
            print(
                f"- {bridge['bridge_id']}: provider={bridge['provider']} "
                f"mode={bridge['mode']} enabled={bridge['enabled']} "
                f"execution={bridge['execution_enabled']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
