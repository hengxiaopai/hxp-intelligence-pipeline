#!/usr/bin/env python3
"""Score and assemble one daily HXP intelligence briefing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.briefing_assembler import build_briefing, render_markdown  # noqa: E402
from pipeline.editorial_scoring import load_weights, score_pool  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", type=Path, required=True, help="候选池 JSON")
    parser.add_argument(
        "--scores",
        type=Path,
        help="已有评分报告；省略时根据候选池即时计算",
    )
    parser.add_argument(
        "--weights",
        type=Path,
        default=ROOT / "config/editorial-weights.json",
        help="编辑评分配置",
    )
    parser.add_argument("--output", type=Path, required=True, help="briefing.json 输出")
    parser.add_argument("--markdown", type=Path, help="可选公开 Markdown 输出")
    return parser.parse_args()


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"JSON 无效：{path}:{exc.lineno}:{exc.colno}") from exc


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def write_json(path: Path, value: dict) -> None:
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main() -> int:
    args = parse_args()
    pool = load_json(args.pool)
    config = load_weights(args.weights)
    scores = load_json(args.scores) if args.scores else score_pool(pool, config)
    briefing = build_briefing(pool, scores, config)
    write_json(args.output, briefing)
    if args.markdown:
        write_text(args.markdown, render_markdown(briefing) + "\n")
    print(
        f"PASS briefing: {args.output} "
        f"({len(briefing['new_items'])} new, "
        f"{len(briefing['continuation_items'])} continuation)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
