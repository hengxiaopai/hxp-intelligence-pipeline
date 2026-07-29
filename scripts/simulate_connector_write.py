#!/usr/bin/env python3
"""Execute one connector request against the offline idempotent simulator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from publishing.connectors.simulator import (  # noqa: E402
    ConnectorSimulationError,
    empty_ledger,
    execute_simulated_draft,
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
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--executed-at", required=True)
    parser.add_argument("--result-output", type=Path, required=True)
    parser.add_argument("--ledger-output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        request = load_json(args.request)
        if args.ledger and args.ledger.exists():
            ledger = load_json(args.ledger)
        else:
            ledger = empty_ledger(updated_at=args.executed_at)
        result, updated = execute_simulated_draft(
            request=request,
            ledger=ledger,
            executed_at=args.executed_at,
        )
        write_json(args.result_output, result)
        write_json(args.ledger_output, updated)
    except (OSError, json.JSONDecodeError, ConnectorSimulationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"PASS connector simulation: {result['status']} {result['simulated_draft_id']}")
    print("external_write_performed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
