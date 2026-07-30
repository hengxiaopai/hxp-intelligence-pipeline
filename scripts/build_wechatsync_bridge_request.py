#!/usr/bin/env python3
"""Build a non-executable Wechatsync bridge request for offline validation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from publishing.bridges import BrowserBridgeError, build_bridge_request  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--operation",
        required=True,
        choices=["list_platforms", "check_auth", "preview_draft", "create_draft"],
    )
    parser.add_argument("--platforms", required=True, help="逗号分隔：zhihu,juejin,csdn")
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--article", type=Path)
    parser.add_argument("--account-ref")
    parser.add_argument(
        "--transport",
        choices=["fixture", "mcp_tool", "cli_dry_run"],
        default="fixture",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        article = None
        if args.article:
            article = json.loads(args.article.read_text(encoding="utf-8"))
        request = build_bridge_request(
            operation=args.operation,
            platforms=args.platforms.split(","),
            created_at=args.created_at,
            article=article,
            account_ref=args.account_ref,
            transport=args.transport,
        )
        schema = json.loads(
            (ROOT / "schemas/browser-bridge-request.schema.json").read_text(
                encoding="utf-8"
            )
        )
        errors = list(
            Draft202012Validator(
                schema, format_checker=FormatChecker()
            ).iter_errors(request)
        )
        if errors:
            raise BrowserBridgeError(
                "Wechatsync请求Schema校验失败："
                + "; ".join(error.message for error in errors)
            )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(request, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (BrowserBridgeError, OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"PASS Wechatsync bridge request: {args.output}")
    print(
        f"request_id={request['bridge_request_id']} "
        f"operation={request['operation']} execution_allowed={request['execution_allowed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
