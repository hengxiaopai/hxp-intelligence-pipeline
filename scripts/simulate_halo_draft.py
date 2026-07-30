#!/usr/bin/env python3
"""Simulate Halo draft creation in-process without a network listener."""

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

from publishing.halo_draft import HaloDraftError  # noqa: E402
from publishing.halo_mock import empty_halo_mock_ledger, simulate_halo_draft  # noqa: E402
from visual.pipeline import write_json  # noqa: E402
from visual.queue import load_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--policy", type=Path, default=ROOT / "config/halo-draft-policy.json")
    parser.add_argument("--executed-at", required=True)
    parser.add_argument("--result-output", type=Path, required=True)
    parser.add_argument("--ledger-output", type=Path, required=True)
    return parser.parse_args()


def schema_errors(payload: Any) -> list[str]:
    validator = Draft202012Validator(
        load_json(ROOT / "schemas/halo-draft-execution.schema.json"),
        format_checker=FormatChecker(),
    )
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
        ledger = load_json(args.ledger) if args.ledger else empty_halo_mock_ledger()
        result, updated_ledger = simulate_halo_draft(
            payload=load_json(args.payload),
            ledger=ledger,
            executed_at=args.executed_at,
            policy=load_json(args.policy),
        )
        errors = schema_errors(result)
        if errors:
            raise HaloDraftError("Halo Mock结果Schema校验失败：\n- " + "\n- ".join(errors))
        write_json(args.result_output, result)
        write_json(args.ledger_output, updated_ledger)
    except (HaloDraftError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        "PASS Halo mock: "
        f"status={result['result']['status']} replayed={result['result']['replayed']} "
        f"external_write={result['external_write_performed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
