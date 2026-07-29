#!/usr/bin/env python3
"""Collect one registered RSS/HTML source into an auditable raw snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collectors import (  # noqa: E402
    CollectionError,
    collect_from_bytes,
    collect_live,
    load_registry_source,
    write_snapshot,
)

DEFAULT_REGISTRY = ROOT / "config/sources.json"
DEFAULT_SNAPSHOT_SCHEMA = ROOT / "schemas/raw-snapshot.schema.json"


class CliError(Exception):
    """Raised for invalid CLI or snapshot output."""


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CliError(f"文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise CliError(f"JSON 无效：{path}:{exc.lineno}:{exc.colno} {exc.msg}") from exc
    if not isinstance(value, dict):
        raise CliError(f"JSON 根节点必须是对象：{path}")
    return value


def validate_snapshot(snapshot: dict, schema_path: Path) -> None:
    schema = load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(snapshot),
        key=lambda error: [str(part) for part in error.absolute_path],
    )
    if errors:
        lines = ["生成的快照未通过 Schema 校验："]
        for error in errors:
            location = "/" + "/".join(str(part) for part in error.absolute_path)
            lines.append(f"- {location or '/'}: {error.message}")
        raise CliError("\n".join(lines))


def default_output_dir() -> Path:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return ROOT / "data/raw" / date


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect one registered RSS/HTML source safely"
    )
    parser.add_argument("--registry-id", required=True)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SNAPSHOT_SCHEMA)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--input-file",
        type=Path,
        help="parse a local fixture; this is the default-safe workflow",
    )
    mode.add_argument(
        "--live",
        action="store_true",
        help="explicitly enable one guarded network request",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--max-items", type=int, default=100)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--print-json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.max_items < 1 or args.max_items > 200:
            raise CliError("--max-items 必须在 1–200 之间")
        if args.timeout < 1 or args.timeout > 60:
            raise CliError("--timeout 必须在 1–60 秒之间")

        source = load_registry_source(args.registry.resolve(), args.registry_id)
        if args.input_file:
            try:
                body = args.input_file.resolve().read_bytes()
            except FileNotFoundError as exc:
                raise CliError(f"fixture 不存在：{args.input_file}") from exc
            snapshot, raw_body = collect_from_bytes(
                source,
                body,
                max_items=args.max_items,
            )
        else:
            snapshot, raw_body = collect_live(
                source,
                max_items=args.max_items,
                timeout=args.timeout,
            )

        output_dir = (args.output_dir or default_output_dir()).resolve()
        metadata_path, body_path, materialized = write_snapshot(
            snapshot,
            raw_body,
            output_dir=output_dir,
        )
        try:
            validate_snapshot(materialized, args.schema.resolve())
        except Exception:
            metadata_path.unlink(missing_ok=True)
            body_path.unlink(missing_ok=True)
            raise

        print(f"PASS snapshot: {metadata_path}")
        print(f"RAW body: {body_path}")
        print(f"ITEMS: {len(materialized['items'])}")
        if materialized["warnings"]:
            for warning in materialized["warnings"]:
                print(f"WARNING: {warning}")
        if args.print_json:
            print(json.dumps(materialized, ensure_ascii=False, indent=2))
    except (CliError, CollectionError) as exc:
        print(f"FAIL\n{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
