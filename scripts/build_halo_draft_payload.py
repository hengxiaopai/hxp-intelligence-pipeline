#!/usr/bin/env python3
"""Build a non-executable Halo draft payload from official request and website package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from publishing.halo_draft import HaloDraftError, build_halo_draft_payload  # noqa: E402
from visual.pipeline import write_json  # noqa: E402
from visual.queue import load_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-request", type=Path, required=True)
    parser.add_argument("--packages", type=Path, required=True)
    parser.add_argument("--policy", type=Path, default=ROOT / "config/halo-draft-policy.json")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        request = load_json(args.official_request)
        package_batch = load_json(args.packages)
        package = next(
            (value for value in package_batch["packages"] if value["platform"] == "website"),
            None,
        )
        if package is None:
            raise HaloDraftError("内容包批次缺少website平台")
        payload = build_halo_draft_payload(
            official_request=request,
            package=package,
            policy=load_json(args.policy),
        )
        write_json(args.output, payload)
    except (HaloDraftError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        "PASS Halo draft payload: "
        f"payload={payload['payload_id']} execution={payload['execution_enabled']} "
        f"external_write={payload['external_write_performed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
