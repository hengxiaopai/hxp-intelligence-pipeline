"""Deterministic editorial scoring for verified, deduplicated candidates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


class EditorialScoringError(ValueError):
    """Raised when editorial inputs or configuration are invalid."""


def load_weights(path: Path) -> dict[str, Any]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EditorialScoringError(f"评分配置不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise EditorialScoringError(
            f"评分配置 JSON 无效：{path}:{exc.lineno}:{exc.colno}"
        ) from exc

    weights = config.get("weights", {})
    total = sum(float(value) for value in weights.values())
    if abs(total - 1.0) > 1e-9:
        raise EditorialScoringError(f"评分权重之和必须为 1.0，当前为 {total:.6f}")
    return config


def _bounded_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise EditorialScoringError(f"{field} 必须是 0–100 的整数")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise EditorialScoringError(f"{field} 必须是 0–100 的整数") from exc
    if number < 0 or number > 100:
        raise EditorialScoringError(f"{field} 超出 0–100：{number}")
    return number


def _risk_penalty(candidate: Mapping[str, Any], config: Mapping[str, Any]) -> int:
    penalties = config["risk_penalties"]
    maximum = int(config["thresholds"]["max_risk_penalty"])
    flags = set(candidate.get("risk_flags", []))
    return min(maximum, sum(int(penalties.get(flag, 0)) for flag in flags))


def _has_direct_evidence(candidate: Mapping[str, Any]) -> bool:
    return any(
        claim.get("support_level") == "direct"
        for claim in candidate.get("evidence_claims", [])
    )


def _decision_for(
    *,
    candidate: Mapping[str, Any],
    dedup: Mapping[str, Any],
    final_score: int,
    config: Mapping[str, Any],
) -> tuple[str, str, list[str]]:
    thresholds = config["thresholds"]
    action = str(dedup.get("action", "keep_new"))
    reasons: list[str] = []

    if action == "reject_duplicate":
        return "rejected", "reject_duplicate", ["3 天窗口内存在同一事件"]
    if action == "reject_no_delta":
        return "rejected", "reject_no_delta", ["连续热点没有可证实的新增变化"]

    confidence = str(candidate.get("preliminary_confidence", "low"))
    if confidence == "low":
        return "rejected", "reject_low_confidence", ["候选事件初步置信度为低"]

    high_risk = set(config.get("high_risk_flags", []))
    if high_risk.intersection(candidate.get("risk_flags", [])) and not _has_direct_evidence(candidate):
        return (
            "manual_review",
            "manual_review",
            ["高风险主题缺少直接证据，必须人工复核"],
        )

    if action == "track_continuation":
        new_delta = str(dedup.get("new_delta") or "").strip()
        if len(new_delta) < 12:
            return "rejected", "reject_no_delta", ["延续跟踪缺少足够具体的 new_delta"]
        if final_score >= int(thresholds["select_continuation"]):
            reasons.append("具有可证实新增变化，可进入延续跟踪")
            return "continuation", "select_continuation", reasons
        return "rejected", "reject_low_impact", ["延续热点综合得分低于准入线"]

    if final_score >= int(thresholds["select_new"]):
        reasons.append("综合得分达到新增事实准入线")
        return "eligible", "select_new", reasons
    if final_score >= int(thresholds["manual_review"]):
        return "manual_review", "manual_review", ["综合得分处于人工复核区间"]
    return "rejected", "reject_low_impact", ["综合得分低于日报准入线"]


def score_entry(entry: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    candidate = entry["candidate"]
    editorial = entry["editorial"]
    dedup = entry["dedup"]

    components = {
        "authority": _bounded_int(candidate["authority_score"], "authority_score"),
        "freshness": _bounded_int(candidate["freshness_score"], "freshness_score"),
        "relevance": _bounded_int(candidate["relevance_score"], "relevance_score"),
        "evidence_quality": _bounded_int(
            editorial["evidence_quality_score"], "evidence_quality_score"
        ),
        "impact": _bounded_int(editorial["impact_score"], "impact_score"),
        "novelty": _bounded_int(editorial["novelty_score"], "novelty_score"),
        "content_value": _bounded_int(
            editorial["content_value_score"], "content_value_score"
        ),
        "product_value": _bounded_int(
            editorial["product_value_score"], "product_value_score"
        ),
    }
    risk_penalty = _risk_penalty(candidate, config)
    components["risk_penalty"] = risk_penalty

    weighted = sum(
        components[name] * float(weight)
        for name, weight in config["weights"].items()
    )
    final_score = max(0, min(100, round(weighted - risk_penalty)))

    confidence = candidate.get("preliminary_confidence")
    if confidence == "low":
        final_score = min(final_score, int(config["thresholds"]["low_confidence_cap"]))
    elif confidence == "observe":
        final_score = min(
            final_score, int(config["thresholds"]["observe_confidence_cap"])
        )

    eligibility, recommended_action, reasons = _decision_for(
        candidate=candidate,
        dedup=dedup,
        final_score=final_score,
        config=config,
    )

    if risk_penalty:
        reasons.append(f"风险项合计扣减 {risk_penalty} 分")
    if candidate.get("evidence_claims"):
        direct = sum(
            claim.get("support_level") == "direct"
            for claim in candidate["evidence_claims"]
        )
        reasons.append(
            f"证据声明 {len(candidate['evidence_claims'])} 条，其中直接证据 {direct} 条"
        )

    return {
        "candidate_id": candidate["candidate_id"],
        "primary_category": candidate["primary_category"],
        "novelty_kind": dedup["novelty_kind"],
        "components": components,
        "final_score": final_score,
        "eligibility": eligibility,
        "recommended_action": recommended_action,
        "reasons": reasons,
        "rank": None,
    }


def score_pool(pool: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    scores = [score_entry(entry, config) for entry in pool.get("entries", [])]
    scores.sort(key=lambda item: (-item["final_score"], item["candidate_id"]))

    rank = 0
    for score in scores:
        if score["recommended_action"] in {"select_new", "select_continuation"}:
            rank += 1
            score["rank"] = rank

    date_compact = str(pool["date"]).replace("-", "")
    return {
        "schema_version": "1.0.0",
        "run_id": f"editorial-score-{date_compact}",
        "date": pool["date"],
        "generated_at": pool["generated_at"],
        "weights_version": config["version"],
        "scores": scores,
    }
