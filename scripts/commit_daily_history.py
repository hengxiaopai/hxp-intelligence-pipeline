#!/usr/bin/env python3
"""Commit one approved daily run into source watermarks and dedup history."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.history_commit import (  # noqa: E402
    HistoryCommitError,
    load_json,
    prepare_history_commit,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--state",
        type=Path,
        default=ROOT / "data/state/source-watermarks.json",
    )
    parser.add_argument(
        "--dedup-index",
        type=Path,
        default=ROOT / "data/state/dedup-index.json",
    )
    parser.add_argument("--state-output", type=Path)
    parser.add_argument("--dedup-output", type=Path)
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="原子覆盖正式状态；省略时仅写 *.next.json 预览",
    )
    return parser.parse_args()


def validate(schema_path: Path, value: dict, label: str) -> None:
    schema = load_json(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(value),
        key=lambda error: [str(part) for part in error.absolute_path],
    )
    if errors:
        messages = [
            f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: "
            f"{error.message}"
            for error in errors
        ]
        raise HistoryCommitError(f"{label} Schema校验失败：\n- " + "\n- ".join(messages))


def atomic_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def next_path(path: Path) -> Path:
    return path.with_name(path.stem + ".next" + path.suffix)


def main() -> int:
    args = parse_args()
    state_output = args.state if args.apply else (args.state_output or next_path(args.state))
    dedup_output = (
        args.dedup_index
        if args.apply
        else (args.dedup_output or next_path(args.dedup_index))
    )
    summary_output = args.summary_output or args.run_dir / "history-commit.json"

    try:
        updated_state, updated_index, summary = prepare_history_commit(
            run_dir=args.run_dir,
            source_state=load_json(args.state),
            dedup_index=load_json(args.dedup_index),
        )
        validate(
            ROOT / "schemas/schedule-state.schema.json",
            updated_state,
            "source-watermarks",
        )
        validate(
            ROOT / "schemas/dedup-index.schema.json",
            updated_index,
            "dedup-index",
        )
    except HistoryCommitError as exc:
        print(f"FAIL history commit: {exc}", file=sys.stderr)
        return 1

    # All calculations and validation finish before any production path changes.
    atomic_write(state_output, updated_state)
    atomic_write(dedup_output, updated_index)
    atomic_write(summary_output, summary)
    mode = "APPLIED" if args.apply else "PREVIEW"
    print(
        f"PASS history commit [{mode}]: "
        f"items={len(summary['committed_item_ids'])}, "
        f"existing={len(summary['already_committed_item_ids'])}, "
        f"registries={len(summary['updated_registry_ids'])}"
    )
    print(f"state: {state_output}")
    print(f"dedup: {dedup_output}")
    print(f"summary: {summary_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
