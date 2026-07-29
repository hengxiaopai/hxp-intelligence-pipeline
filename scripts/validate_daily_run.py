#!/usr/bin/env python3
"""Validate one archived HXP daily run and reproduce its generated outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_daily_pipeline import (  # noqa: E402
    DailyRunError,
    assert_schema,
    load_json,
    run_daily,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--weights",
        type=Path,
        default=ROOT / "config/editorial-weights.json",
    )
    parser.add_argument(
        "--run-config",
        type=Path,
        default=ROOT / "config/daily-run.json",
    )
    return parser.parse_args()


def _resolve_recorded_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _verify_artifact(artifact: dict) -> None:
    path = _resolve_recorded_path(artifact["path"])
    if not path.is_file():
        raise DailyRunError(f"归档文件不存在：{path}")
    body = path.read_bytes()
    digest = hashlib.sha256(body).hexdigest()
    if digest != artifact["sha256"]:
        raise DailyRunError(f"归档哈希不一致：{path}")
    if len(body) != artifact["byte_size"]:
        raise DailyRunError(f"归档字节数不一致：{path}")


def validate_daily(run_dir: Path, weights: Path, run_config: Path) -> None:
    run_dir = run_dir.resolve()
    run_record = load_json(run_dir / "run.json")
    assert_schema(ROOT / "schemas/daily-run.schema.json", run_record, "run.json")

    artifacts = run_record["artifacts"]
    for key in (
        "candidate_pool",
        "editorial_scores",
        "briefing_json",
        "briefing_markdown",
    ):
        _verify_artifact(artifacts[key])
    for artifact in artifacts["sources"]:
        _verify_artifact(artifact)

    scores = load_json(run_dir / "editorial-scores.json")
    briefing = load_json(run_dir / "briefing.json")
    assert_schema(ROOT / "schemas/editorial-score.schema.json", scores, "scores")
    assert_schema(ROOT / "schemas/briefing.schema.json", briefing, "briefing")

    markdown = (run_dir / "briefing.md").read_text(encoding="utf-8")
    config = load_json(run_config)
    forbidden = [
        marker
        for marker in config.get("forbidden_public_markdown_markers", [])
        if marker in markdown
    ]
    if forbidden:
        raise DailyRunError(f"公开 Markdown 包含内部标记：{forbidden}")

    if run_record["review_status"] != "approved" and run_record["publication_allowed"]:
        raise DailyRunError("未通过人工审核时 publication_allowed 不能为 true")

    with tempfile.TemporaryDirectory() as directory:
        replay_dir = Path(directory) / run_dir.name
        replay_dir.mkdir(parents=True)
        shutil.copy2(run_dir / "candidate-pool.json", replay_dir / "candidate-pool.json")
        shutil.copytree(run_dir / "sources", replay_dir / "sources")
        run_daily(
            run_dir=replay_dir,
            weights_path=weights,
            config_path=run_config,
            mode=run_record["mode"],
            review_status=run_record["review_status"],
        )
        for filename in ("editorial-scores.json", "briefing.json", "briefing.md"):
            archived = (run_dir / filename).read_bytes()
            reproduced = (replay_dir / filename).read_bytes()
            if archived != reproduced:
                raise DailyRunError(f"重放结果不一致：{filename}")


def main() -> int:
    args = parse_args()
    try:
        validate_daily(args.run_dir, args.weights, args.run_config)
    except DailyRunError as exc:
        print(f"FAIL daily validation: {exc}", file=sys.stderr)
        return 1
    print(f"PASS daily validation: {args.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
