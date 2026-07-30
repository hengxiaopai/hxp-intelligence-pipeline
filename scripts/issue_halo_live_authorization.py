#!/usr/bin/env python3
"""Issue a non-secret, time-limited, draft-only Halo authorization record."""

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

from publishing.halo_draft import HaloDraftError, issue_halo_live_authorization  # noqa: E402
from visual.pipeline import write_json  # noqa: E402
from visual.queue import load_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-request", type=Path, required=True)
    parser.add_argument("--site-origin", required=True)
    parser.add_argument("--site-fingerprint", required=True)
    parser.add_argument("--halo-version", required=True)
    parser.add_argument("--account-ref", required=True)
    parser.add_argument("--issued-at", required=True)
    parser.add_argument("--expires-at", required=True)
    parser.add_argument("--issued-by", required=True)
    parser.add_argument("--confirm-draft-only", action="store_true")
    parser.add_argument("--policy", type=Path, default=ROOT / "config/halo-draft-policy.json")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def schema_errors(payload: Any) -> list[str]:
    validator = Draft202012Validator(
        load_json(ROOT / "schemas/halo-live-authorization.schema.json"),
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
        authorization = issue_halo_live_authorization(
            official_request=load_json(args.official_request),
            site_origin=args.site_origin,
            site_fingerprint=args.site_fingerprint,
            halo_version=args.halo_version,
            account_ref=args.account_ref,
            issued_at=args.issued_at,
            expires_at=args.expires_at,
            issued_by=args.issued_by,
            user_confirmed_draft_only=args.confirm_draft_only,
            policy=load_json(args.policy),
        )
        errors = schema_errors(authorization)
        if errors:
            raise HaloDraftError("Halo授权Schema校验失败：\n- " + "\n- ".join(errors))
        write_json(args.output, authorization)
    except (HaloDraftError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        "PASS Halo live authorization record: "
        f"status={authorization['status']} publish={authorization['publish_allowed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
