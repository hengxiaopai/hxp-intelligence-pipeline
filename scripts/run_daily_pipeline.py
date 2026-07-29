#!/usr/bin/env python3
"""Run the offline daily pipeline from an archived candidate pool and sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.briefing_assembler import build_briefing, render_markdown  # noqa: E402
from pipeline.editorial_scoring import load_weights, score_pool  # noqa: E402


class DailyRunError(ValueError):
    """Raised when a daily run cannot be safely generated."""


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
    parser.add_argument(
        "--mode",
        choices=["fixture", "archived_real_sources", "live"],
        default="archived_real_sources",
    )
    parser.add_argument(
        "--review-status",
        choices=["pending", "approved", "rejected"],
        default="pending",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DailyRunError(f"文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise DailyRunError(
            f"JSON 无效：{path}:{exc.lineno}:{exc.colno}"
        ) from exc


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def write_json(path: Path, value: dict[str, Any]) -> None:
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _schema_errors(schema_path: Path, value: Any) -> list[str]:
    schema = load_json(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(value),
        key=lambda error: [str(part) for part in error.absolute_path],
    )
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: "
        f"{error.message}"
        for error in errors
    ]


def assert_schema(schema_path: Path, value: Any, label: str) -> None:
    errors = _schema_errors(schema_path, value)
    if errors:
        raise DailyRunError(f"{label} Schema 校验失败：\n- " + "\n- ".join(errors))


def _relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _artifact(path: Path) -> dict[str, Any]:
    body = path.read_bytes()
    return {
        "path": _relative(path),
        "sha256": hashlib.sha256(body).hexdigest(),
        "byte_size": len(body),
    }


def _source_records(source_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    files = sorted(source_dir.glob("*.json"))
    if not files:
        raise DailyRunError(f"来源目录中没有 JSON：{source_dir}")
    records: list[tuple[Path, dict[str, Any]]] = []
    seen: set[str] = set()
    for path in files:
        record = load_json(path)
        source_id = str(record.get("source_id", ""))
        if not source_id:
            raise DailyRunError(f"来源缺少 source_id：{path}")
        if source_id in seen:
            raise DailyRunError(f"来源 ID 重复：{source_id}")
        seen.add(source_id)
        assert_schema(ROOT / "schemas/source.schema.json", record, str(path))
        records.append((path, record))
    return records


def _candidate_source_references(
    pool: dict[str, Any],
    source_records: Iterable[tuple[Path, dict[str, Any]]],
) -> bool:
    known = {record["source_id"] for _, record in source_records}
    referenced: set[str] = set()
    for entry in pool.get("entries", []):
        candidate = entry.get("candidate", {})
        assert_schema(
            ROOT / "schemas/candidate.schema.json",
            candidate,
            str(candidate.get("candidate_id", "candidate")),
        )
        candidate_sources = set(candidate.get("source_ids", []))
        claim_sources = {
            claim.get("source_id") for claim in candidate.get("evidence_claims", [])
        }
        if not claim_sources.issubset(candidate_sources):
            missing = sorted(claim_sources.difference(candidate_sources))
            raise DailyRunError(
                f"证据声明引用未列入 candidate.source_ids：{missing}"
            )
        referenced.update(candidate_sources)
    missing_records = sorted(referenced.difference(known))
    if missing_records:
        raise DailyRunError(f"候选引用缺少来源记录：{missing_records}")
    unused = sorted(known.difference(referenced))
    if unused:
        raise DailyRunError(f"来源记录未被候选引用：{unused}")
    return True


def _public_markdown_safe(markdown: str, config: dict[str, Any]) -> bool:
    forbidden = config.get("forbidden_public_markdown_markers", [])
    found = [marker for marker in forbidden if marker in markdown]
    if found:
        raise DailyRunError(f"公开 Markdown 包含内部标记：{found}")
    return True


def run_daily(
    *,
    run_dir: Path,
    weights_path: Path,
    config_path: Path,
    mode: str,
    review_status: str,
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    candidate_pool_path = run_dir / "candidate-pool.json"
    source_dir = run_dir / "sources"
    score_path = run_dir / "editorial-scores.json"
    briefing_path = run_dir / "briefing.json"
    markdown_path = run_dir / "briefing.md"
    run_path = run_dir / "run.json"

    pool = load_json(candidate_pool_path)
    config = load_json(config_path)
    weights = load_weights(weights_path)
    source_records = _source_records(source_dir)
    candidate_refs_valid = _candidate_source_references(pool, source_records)

    first_scores = score_pool(pool, weights)
    second_scores = score_pool(pool, weights)
    if first_scores != second_scores:
        raise DailyRunError("相同候选池产生了不一致的评分结果")

    first_briefing = build_briefing(pool, first_scores, weights)
    second_briefing = build_briefing(pool, second_scores, weights)
    if first_briefing != second_briefing:
        raise DailyRunError("相同候选池产生了不一致的简报结果")

    first_markdown = render_markdown(first_briefing) + "\n"
    second_markdown = render_markdown(second_briefing) + "\n"
    deterministic = (
        first_scores == second_scores
        and first_briefing == second_briefing
        and first_markdown == second_markdown
    )

    assert_schema(
        ROOT / "schemas/editorial-score.schema.json",
        first_scores,
        "editorial-scores.json",
    )
    assert_schema(
        ROOT / "schemas/briefing.schema.json",
        first_briefing,
        "briefing.json",
    )
    markdown_safe = _public_markdown_safe(first_markdown, config)

    write_json(score_path, first_scores)
    write_json(briefing_path, first_briefing)
    write_text(markdown_path, first_markdown)

    validation_values = {
        "candidate_source_references": candidate_refs_valid,
        "source_schema": True,
        "score_schema": True,
        "briefing_schema": True,
        "artifact_hashes": True,
        "public_markdown_safe": markdown_safe,
        "deterministic_outputs": deterministic,
    }
    validated = all(validation_values.values())
    publication_allowed = validated and review_status == "approved"
    date_compact = str(pool["date"]).replace("-", "")

    run_record = {
        "schema_version": "1.0.0",
        "run_id": f"daily-run-{date_compact}",
        "date": pool["date"],
        "timezone": pool.get("timezone", config.get("timezone", "Asia/Shanghai")),
        "generated_at": pool["generated_at"],
        "mode": mode,
        "status": "validated" if validated else "failed",
        "review_status": review_status,
        "publication_allowed": publication_allowed,
        "source_count": len(source_records),
        "selected_counts": {
            "new_items": len(first_briefing["new_items"]),
            "continuation_items": len(first_briefing["continuation_items"]),
            "rejected_candidates": len(first_briefing.get("rejected_candidates", [])),
        },
        "artifacts": {
            "candidate_pool": _artifact(candidate_pool_path),
            "editorial_scores": _artifact(score_path),
            "briefing_json": _artifact(briefing_path),
            "briefing_markdown": _artifact(markdown_path),
            "sources": [_artifact(path) for path, _ in source_records],
        },
        "validations": validation_values,
        "notes": [
            "该运行使用已归档并人工核对的一手来源，不在 CI 中访问外网。",
            "review_status=pending 时 publication_allowed 必须保持 false。",
            "正式海报须在人工审核通过后单独生成。",
        ],
    }
    assert_schema(ROOT / "schemas/daily-run.schema.json", run_record, "run.json")
    write_json(run_path, run_record)
    return run_record


def main() -> int:
    args = parse_args()
    try:
        result = run_daily(
            run_dir=args.run_dir,
            weights_path=args.weights,
            config_path=args.run_config,
            mode=args.mode,
            review_status=args.review_status,
        )
    except DailyRunError as exc:
        print(f"FAIL daily run: {exc}", file=sys.stderr)
        return 1
    print(
        f"PASS daily run: {result['run_id']} "
        f"({result['selected_counts']['new_items']} new, "
        f"{result['selected_counts']['continuation_items']} continuation, "
        f"review={result['review_status']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
