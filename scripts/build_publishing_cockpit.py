#!/usr/bin/env python3
"""Render a single-file offline publishing cockpit from a handoff manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from publishing.cockpit import CockpitError, render_cockpit_html  # noqa: E402
from visual.queue import load_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        render_cockpit_html(load_json(args.manifest), output_path=args.output)
    except (CockpitError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"PASS publishing cockpit: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
