#!/usr/bin/env python3
"""Validate a candidate event against its source record and source registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


class CandidateValidationError(Exception):
    """Raised when candidate bundle consistency checks fail."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError as exc:
        raise CandidateValidationError(f"文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise CandidateValidationError(
            f"JSON 解析失败：{path}:{exc.lineno}:{exc.colno} {exc.msg}"
        ) from exc
    if not isinstance(value, dict):
        raise CandidateValidationError(f"JSON 根节点必须是对象：{path}")
    return value


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate_bundle(
    candidate: dict[str, Any],
    source: dict[str, Any],
    registry: dict[str, Any],
) -> list[str]:
    errors: list[str] = []

    source_id = source["source_id"]
    candidate_source_ids = set(candidate["source_ids"])
    candidate_source_urls = {url.rstrip("/") for url in candidate["source_urls"]}

    require(
        source_id in candidate_source_ids,
        "candidate.source_ids 必须包含对应 source.source_id",
        errors,
    )
    require(
        source["url"].rstrip("/") in candidate_source_urls,
        "candidate.source_urls 必须包含对应 source.url",
        errors,
    )

    registry_sources = {
        item["registry_id"]: item for item in registry.get("sources", [])
    }
    registry_id = candidate["ingestion"]["source_registry_id"]
    require(
        registry_id in registry_sources,
        f"candidate 引用了不存在的 source_registry_id：{registry_id}",
        errors,
    )

    if registry_id in registry_sources:
        registry_source = registry_sources[registry_id]
        require(
            candidate["ingestion"]["collection_method"]
            == registry_source["collection_method"],
            "candidate.ingestion.collection_method 必须与注册表一致",
            errors,
        )
        require(
            source["publisher"] == registry_source["publisher"],
            "source.publisher 必须与注册表发布主体一致",
            errors,
        )
        require(
            source["authority_level"] == registry_source["authority_level"],
            "source.authority_level 必须与注册表一致",
            errors,
        )

    evidence_source_ids = {
        item["source_id"] for item in candidate["evidence_claims"]
    }
    require(
        evidence_source_ids.issubset(candidate_source_ids),
        "每条 evidence_claim.source_id 必须包含在 candidate.source_ids 中",
        errors,
    )

    risk_flags = set(candidate["risk_flags"])
    require(
        not ("none" in risk_flags and len(risk_flags) > 1),
        "risk_flags 中 none 不能与其他风险并存",
        errors,
    )

    if candidate["preliminary_confidence"] == "high":
        require(
            source["authority_level"] == "tier_1_official",
            "high 置信度候选至少需要 Tier 1 主来源",
            errors,
        )
        require(
            any(
                claim["support_level"] == "direct"
                for claim in candidate["evidence_claims"]
            ),
            "high 置信度候选至少需要一条 direct 证据",
            errors,
        )
        require(
            source["verification_status"] in {"verified", "cross_checked"},
            "high 置信度候选的来源必须 verified 或 cross_checked",
            errors,
        )

    if candidate["status"] == "rejected":
        require(
            candidate.get("rejection_reason") is not None,
            "status=rejected 时必须填写 rejection_reason",
            errors,
        )
    else:
        require(
            candidate.get("rejection_reason") is None,
            "非 rejected 状态下 rejection_reason 必须为 null",
            errors,
        )

    require(
        candidate["dedup_keys"]["date_bucket"] == candidate["event_date"],
        "dedup_keys.date_bucket 必须与 event_date 一致",
        errors,
    )
    require(
        set(candidate["dedup_keys"]["entities"])
        == set(candidate["canonical_entities"]),
        "dedup_keys.entities 必须与 canonical_entities 一致",
        errors,
    )

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a candidate bundle")
    parser.add_argument(
        "--candidate",
        type=Path,
        default=ROOT / "data/examples/candidate.example.json",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT / "data/examples/candidate-source.example.json",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=ROOT / "config/sources.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        candidate = load_json(args.candidate.resolve())
        source = load_json(args.source.resolve())
        registry = load_json(args.registry.resolve())
        errors = validate_bundle(candidate, source, registry)
        if errors:
            raise CandidateValidationError(
                "\n".join(f"- {error}" for error in errors)
            )
        print(
            "PASS candidate bundle: "
            f"{candidate['candidate_id']} -> {source['source_id']} -> "
            f"{candidate['ingestion']['source_registry_id']}"
        )
    except CandidateValidationError as exc:
        print(f"FAIL\n{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
