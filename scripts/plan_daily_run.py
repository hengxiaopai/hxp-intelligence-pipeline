#!/usr/bin/env python3
"""Generate a deterministic daily source plan from registry watermarks."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.scheduler import build_daily_plan, parse_datetime  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        type=Path,
        default=ROOT / "config/sources.json",
    )
    parser.add_argument(
        "--state",
        type=Path,
        default=ROOT / "data/state/source-watermarks.json",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config/schedule.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--now",
        help="ISO 8601时间；省略时使用当前UTC时间",
    )
    parser.add_argument(
        "--mode",
        choices=["plan_only", "fixture", "live"],
        default="plan_only",
    )
    parser.add_argument("--live-enabled", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"JSON无效：{path}:{exc.lineno}:{exc.colno}") from exc


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    args = parse_args()
    now = parse_datetime(args.now) if args.now else datetime.now(timezone.utc)
    plan = build_daily_plan(
        registry=load_json(args.registry),
        state=load_json(args.state),
        config=load_json(args.config),
        now=now,
        mode=args.mode,
        live_enabled=args.live_enabled,
    )
    write_json(args.output, plan)
    summary = plan["summary"]
    print(
        f"PASS daily plan: {args.output} "
        f"(due={summary['due_sources']}, live={summary['live_collectable']}, "
        f"manual={summary['manual_review']}, blocked={summary['blocked_sources']}, "
        f"deferred={summary['deferred_sources']})"
    )
    for item in plan["due_sources"]:
        print(
            f"P{item['priority']} {item['action']:<14} "
            f"{item['due_reason']:<30} {item['registry_id']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
