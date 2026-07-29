#!/usr/bin/env python3
"""Issue one exact, time-limited connector authorization for an approved entry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from publishing.connector_gate import ConnectorGateError, issue_connector_authorization  # noqa: E402
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
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--connector-id", required=True)
    parser.add_argument("--entry-id", required=True)
    parser.add_argument("--account-ref", required=True)
    parser.add_argument("--issued-at", required=True)
    parser.add_argument("--expires-at", required=True)
    parser.add_argument("--issued-by", required=True)
    parser.add_argument("--credential-reference")
    parser.add_argument("--registry", type=Path, default=ROOT / "config/connectors.json")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        plan = load_json(args.plan)
        entries = {value["entry_id"]: value for value in plan.get("entries", [])}
        if args.entry_id not in entries:
            raise ConnectorGateError(f"发布计划中不存在条目：{args.entry_id}")
        registry = load_connector_registry(args.registry)
        connector = select_connector(registry, connector_id=args.connector_id)
        authorization = issue_connector_authorization(
            connector=connector,
            entry=entries[args.entry_id],
            account_ref=args.account_ref,
            issued_at=args.issued_at,
            expires_at=args.expires_at,
            issued_by=args.issued_by,
            credential_reference=args.credential_reference,
        )
        write_json(args.output, authorization)
    except (OSError, json.JSONDecodeError, ConnectorRegistryError, ConnectorGateError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"PASS connector authorization: {authorization['authorization_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
