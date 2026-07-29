#!/usr/bin/env python3
"""Score one editorial candidate pool deterministically."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.editorial_scoring import load_weights, score_pool  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", type=Path, required=True, help="候选池 JSON")
    parser.add_argument(
        "--weights",
        type=Path,
        default=ROOT / "config/editorial-weights.json",
        help="编辑评分配置",
    )
    parser.add_argument("--output", type=Path, required=True, help="评分报告输出路径")
    return parser.parse_args()


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"JSON 无效：{path}:{exc.lineno}:{exc.colno}") from exc


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
    report = score_pool(load_json(args.pool), load_weights(args.weights))
    write_json(args.output, report)
    print(f"PASS editorial scores: {args.output}")
    for score in report["scores"]:
        print(
            f"{score['rank'] or '-':>2} {score['final_score']:>3} "
            f"{score['recommended_action']:<22} {score['candidate_id']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
