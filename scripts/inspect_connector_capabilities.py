#!/usr/bin/env python3
"""Validate and print the disabled-by-default connector capability registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from publishing.connectors.registry import (  # noqa: E402
    ConnectorRegistryError,
    load_connector_registry,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=ROOT / "config/connectors.json")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        registry = load_connector_registry(args.registry)
    except ConnectorRegistryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    rows = [
        {
            "connector_id": value["connector_id"],
            "platform": value["platform"],
            "mode": value["mode"],
            "enabled": value["enabled"],
            "allowed_actions": value["allowed_actions"],
        }
        for value in registry["connectors"]
    ]
    if args.json:
        print(json.dumps({"real_writes_enabled": False, "connectors": rows}, ensure_ascii=False, indent=2))
    else:
        print("real_writes_enabled=false")
        for row in rows:
            print(
                f"{row['connector_id']}: platform={row['platform']} mode={row['mode']} "
                f"enabled={str(row['enabled']).lower()} actions={','.join(row['allowed_actions'])}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
