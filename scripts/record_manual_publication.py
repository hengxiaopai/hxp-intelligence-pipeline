#!/usr/bin/env python3
"""Create or update a user-confirmed manual publication session."""

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

from publishing.cockpit import (  # noqa: E402
    CockpitError,
    build_initial_session,
    update_manual_record,
)
from visual.pipeline import write_json  # noqa: E402
from visual.queue import load_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--session", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--updated-at", required=True)
    parser.add_argument("--session-slug", default="manual")
    parser.add_argument("--platform", choices=["wechat", "xiaohongshu", "douyin", "x", "website", "zhihu"])
    parser.add_argument("--status", choices=["not_started", "opened", "pasted", "draft_saved", "published", "failed", "skipped"])
    parser.add_argument("--confirmed-by-user", action="store_true")
    parser.add_argument("--external-content-id")
    parser.add_argument("--external-url")
    parser.add_argument("--notes")
    return parser.parse_args()


def schema_errors(schema_path: Path, payload: Any) -> list[str]:
    validator = Draft202012Validator(load_json(schema_path), format_checker=FormatChecker())
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
        manifest = load_json(args.manifest)
        if args.session:
            session = load_json(args.session)
        else:
            session = build_initial_session(
                manifest,
                created_at=args.updated_at,
                session_slug=args.session_slug,
            )
        if bool(args.platform) != bool(args.status):
            raise CockpitError("--platform 与 --status 必须同时提供")
        if args.platform and args.status:
            session = update_manual_record(
                session=session,
                manifest=manifest,
                platform=args.platform,
                status=args.status,
                updated_at=args.updated_at,
                confirmed_by_user=args.confirmed_by_user,
                external_content_id=args.external_content_id,
                external_url=args.external_url,
                notes=args.notes,
            )
        errors = schema_errors(ROOT / "schemas/cockpit-session.schema.json", session)
        if errors:
            raise CockpitError("Cockpit Session Schema校验失败：\n- " + "\n- ".join(errors))
        write_json(args.output, session)
    except (CockpitError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        "PASS cockpit session: "
        f"published={session['summary']['published']} draft_saved={session['summary']['draft_saved']} "
        f"external_write={session['external_write_performed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
