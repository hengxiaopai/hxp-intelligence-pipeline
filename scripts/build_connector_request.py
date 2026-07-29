#!/usr/bin/env python3
"""Consume an authorization and build one exact connector request."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from publishing.connector_gate import ConnectorGateError, build_connector_request  # noqa: E402
from publishing.connectors.registry import (  # noqa: E402
    ConnectorRegistryError,
    load_connector_registry,
    select_connector,
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--package-id", required=True)
    parser.add_argument("--account-ref", required=True)
    parser.add_argument("--requested-at", required=True)
    parser.add_argument("--registry", type=Path, default=ROOT / "config/connectors.json")
    parser.add_argument("--request-output", type=Path, required=True)
    parser.add_argument("--authorization-output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        authorization = load_json(args.authorization)
        plan = load_json(args.plan)
        entries = {value["entry_id"]: value for value in plan.get("entries", [])}
        entry_id = str(authorization.get("entry_id", ""))
        if entry_id not in entries:
            raise ConnectorGateError(f"发布计划中不存在授权条目：{entry_id}")
        registry = load_connector_registry(args.registry)
        connector = select_connector(registry, connector_id=str(authorization.get("connector_id", "")))
        request, consumed = build_connector_request(
            authorization=authorization,
            connector=connector,
            entry=entries[entry_id],
            package_id=args.package_id,
            account_ref=args.account_ref,
            requested_at=args.requested_at,
        )
        write_json(args.request_output, request)
        write_json(args.authorization_output, consumed)
    except (OSError, json.JSONDecodeError, ConnectorRegistryError, ConnectorGateError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"PASS connector request: {request['request_id']}")
    print(f"authorization_status={consumed['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
