#!/usr/bin/env python3
"""Import generated main visuals and bind them to requests with hashes and dimensions."""

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

from visual.pipeline import write_json  # noqa: E402
from visual.queue import load_json  # noqa: E402
from visual.result_import import VisualImportError, import_visual_results  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--generator-reference", required=True)
    parser.add_argument("--imported-at")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--replace-existing", action="store_true")
    return parser.parse_args()


def schema_errors(schema_path: Path, value: Any) -> list[str]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(
            validator.iter_errors(value),
            key=lambda error: [str(part) for part in error.absolute_path],
        )
    ]


def main() -> int:
    args = parse_args()
    try:
        request_queue = load_json(args.requests)
        imported = import_visual_results(
            request_queue=request_queue,
            result_dir=args.result_dir,
            generator_reference=args.generator_reference,
            imported_at=args.imported_at,
            require_all=not args.allow_partial,
            replace_existing=args.replace_existing,
        )
        errors = schema_errors(ROOT / "schemas/visual-request.schema.json", imported)
        if errors:
            raise VisualImportError(
                "导入结果Schema校验失败：\n- " + "\n- ".join(errors)
            )
        write_json(args.output, imported)
    except (VisualImportError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    total = len(imported["requests"])
    imported_count = sum(request["result"] is not None for request in imported["requests"])
    print(
        f"PASS visual import: {args.output} imported={imported_count}/{total}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
