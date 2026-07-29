#!/usr/bin/env python3
"""Execute only explicitly live-eligible sources from a validated daily plan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collectors.base import CollectionError, load_registry_source  # noqa: E402
from collectors.snapshot import collect_live, write_snapshot  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument(
        "--registry",
        type=Path,
        default=ROOT / "config/sources.json",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-items", type=int, default=100)
    parser.add_argument("--timeout", type=int, default=15)
    return parser.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    args = parse_args()
    plan = load_json(args.plan)
    if plan.get("mode") != "live" or plan.get("live_enabled") is not True:
        print("FAIL collection plan: plan is not explicitly live-enabled", file=sys.stderr)
        return 2

    failures: list[str] = []
    completed = 0
    for item in plan.get("due_sources", []):
        if item.get("action") != "collect_live":
            continue
        registry_id = item["registry_id"]
        if item.get("live_eligible") is not True:
            failures.append(f"{registry_id}: live_eligible=false")
            continue
        try:
            source = load_registry_source(args.registry, registry_id)
            snapshot, body = collect_live(
                source,
                max_items=args.max_items,
                timeout=args.timeout,
            )
            metadata, raw, _ = write_snapshot(
                snapshot,
                body,
                output_dir=args.output_dir / registry_id,
            )
            completed += 1
            print(f"PASS collect: {registry_id} -> {metadata} / {raw}")
        except (CollectionError, OSError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"{registry_id}: {type(exc).__name__}: {exc}")

    if failures:
        print("FAIL live collection:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(f"PASS collection plan: completed={completed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
