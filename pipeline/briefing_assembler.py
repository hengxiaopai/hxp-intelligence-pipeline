"""Assemble a validated daily briefing from scored editorial candidates."""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence


class BriefingAssemblyError(ValueError):
    """Raised when selected inputs cannot form a trustworthy briefing."""


BRIEFING_RISK_FLAGS = {
    "unconfirmed",
    "policy_in_discussion",
    "financial_not_audited",
    "market_data_time_sensitive",
    "investment_advice_risk",
    "copyright_risk",
    "platform_review_risk",
    "security_sensitive",
    "brand_affiliation_risk",
    "none",
}

REJECTION_REASON_BY_ACTION = {
    "reject_duplicate": "duplicate_event",
    "reject_no_delta": "no_new_delta",
    "reject_low_confidence": "low_confidence",
    "reject_low_impact": "low_impact",
    "manual_review": "insufficient_sources",
}


def _index_entries(pool: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for entry in pool.get("entries", []):
        candidate_id = entry["candidate"]["candidate_id"]
        if candidate_id in result:
            raise BriefingAssemblyError(f"候选 ID 重复：{candidate_id}")
        result[candidate_id] = entry
    return result


def _select_new_scores(
    scores: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    selection = config["selection"]
    maximum = int(selection["target_max_new_items"])
    minimum = int(selection["target_min_new_items"])
    category_cap = int(selection["category_soft_cap"])

    eligible = [
        score
        for score in scores
        if score["recommended_action"] == "select_new"
        and score["novelty_kind"] in {"new_theme", "new_angle"}
    ]
    eligible.sort(key=lambda item: (-item["final_score"], item["candidate_id"]))

    selected: list[Mapping[str, Any]] = []
    overflow: list[Mapping[str, Any]] = []
    counts: Counter[str] = Counter()
    for score in eligible:
        category = str(score["primary_category"])
        if counts[category] >= category_cap:
            overflow.append(score)
            continue
        selected.append(score)
        counts[category] += 1
        if len(selected) == maximum:
            return selected

    for score in overflow:
        if len(selected) >= maximum:
            break
        selected.append(score)

    if len(selected) < minimum:
        already = {item["candidate_id"] for item in selected}
        for score in eligible:
            if score["candidate_id"] in already:
                continue
            selected.append(score)
            if len(selected) >= min(minimum, maximum):
                break
    return selected[:maximum]


def _select_continuation_scores(
    scores: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    maximum = int(config["selection"]["max_continuation_items"])
    selected = [
        score
        for score in scores
        if score["recommended_action"] == "select_continuation"
    ]
    selected.sort(key=lambda item: (-item["final_score"], item["candidate_id"]))
    return selected[:maximum]


def _confidence(candidate: Mapping[str, Any], score: Mapping[str, Any]) -> dict[str, Any]:
    evidence_count = len(candidate.get("evidence_claims", []))
    authority = int(candidate["authority_score"])
    evidence_quality = int(score["components"]["evidence_quality"])
    confidence_score = round((authority + evidence_quality) / 2)
    level = str(candidate["preliminary_confidence"])
    rationale = (
        f"来源权威度 {authority}，证据质量 {evidence_quality}，"
        f"共记录 {evidence_count} 条证据声明。"
    )
    return {
        "level": level,
        "score": confidence_score,
        "rationale": rationale,
        "evidence_count": evidence_count,
    }


def _risk_flags(candidate: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    for flag in candidate.get("risk_flags", []):
        if flag == "community_content":
            flag = "unconfirmed"
        if flag in BRIEFING_RISK_FLAGS and flag not in result:
            result.append(flag)
    if not result:
        result.append("none")
    if len(result) > 1 and "none" in result:
        result.remove("none")
    return result


def _make_base_item(
    *,
    entry: Mapping[str, Any],
    score: Mapping[str, Any],
    item_id: str,
    generated_at: str,
    status: str,
) -> dict[str, Any]:
    candidate = entry["candidate"]
    editorial = entry["editorial"]
    item = {
        "item_id": item_id,
        "event_fingerprint": candidate["event_fingerprint"],
        "status": status,
        "title": editorial["public_title"],
        "subtitle": editorial.get("subtitle", ""),
        "summary": editorial["summary"],
        "primary_category": candidate["primary_category"],
        "information_types": candidate["information_types"],
        "confidence": _confidence(candidate, score),
        "importance_score": score["final_score"],
        "novelty_score": int(editorial["novelty_score"]),
        "why_it_matters": editorial["why_it_matters"],
        "follow_up": editorial["follow_up"],
        "conversion_directions": editorial["conversion_directions"],
        "audiences": editorial["audiences"],
        "source_ids": candidate["source_ids"],
        "primary_source_id": candidate["source_ids"][0],
        "first_seen": candidate["observed_at"],
        "last_updated": generated_at,
        "selected_reason": editorial["selected_reason"],
        "risk_flags": _risk_flags(candidate),
        "visual_brief": editorial["visual_brief"],
    }
    if not item["subtitle"]:
        item.pop("subtitle")
    return item


def _new_item(
    entry: Mapping[str, Any],
    score: Mapping[str, Any],
    item_id: str,
    generated_at: str,
) -> dict[str, Any]:
    return _make_base_item(
        entry=entry,
        score=score,
        item_id=item_id,
        generated_at=generated_at,
        status="new",
    )


def _continuation_item(
    entry: Mapping[str, Any],
    score: Mapping[str, Any],
    item_id: str,
    generated_at: str,
) -> dict[str, Any]:
    item = _make_base_item(
        entry=entry,
        score=score,
        item_id=item_id,
        generated_at=generated_at,
        status="continuation",
    )
    dedup = entry["dedup"]
    previous = dedup.get("previous_item_ids", [])
    if not previous:
        raise BriefingAssemblyError(
            f"延续候选缺少 previous_item_ids：{entry['candidate']['candidate_id']}"
        )
    item["continuation"] = {
        "previous_item_ids": previous,
        "new_delta": dedup["new_delta"],
        "background_repeated": False,
    }
    return item


def _source_requirements_met(
    selected_entries: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> bool:
    high_risk = set(config.get("high_risk_flags", []))
    for entry in selected_entries:
        candidate = entry["candidate"]
        if not candidate.get("source_ids") or not candidate.get("evidence_claims"):
            return False
        flags = high_risk.intersection(candidate.get("risk_flags", []))
        if flags and not any(
            claim.get("support_level") == "direct"
            for claim in candidate.get("evidence_claims", [])
        ):
            return False
    return True


def _content_opportunities(
    pool: Mapping[str, Any],
    candidate_to_item: Mapping[str, str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    date_compact = str(pool["date"]).replace("-", "")
    for sequence, raw in enumerate(pool.get("content_opportunities", []), start=1):
        related: list[str] = []
        for candidate_id in raw["related_candidate_ids"]:
            item_id = candidate_to_item.get(candidate_id)
            if item_id is None:
                raise BriefingAssemblyError(
                    f"内容机会引用了未入选候选：{candidate_id}"
                )
            related.append(item_id)
        result.append(
            {
                "opportunity_id": f"content-{date_compact}-{sequence:02d}",
                "wechat_title": raw["wechat_title"],
                "douyin_title": raw["douyin_title"],
                "angle": raw["angle"],
                "visual_direction": raw["visual_direction"],
                "related_item_ids": list(dict.fromkeys(related)),
            }
        )
    if len(result) != 3:
        raise BriefingAssemblyError("公开简报必须提供且仅提供 3 个内容机会")
    return result


def _product_opportunity(
    pool: Mapping[str, Any],
    candidate_to_item: Mapping[str, str],
) -> dict[str, Any] | None:
    raw = pool.get("product_opportunity")
    if raw is None:
        return None

    gates = raw["gates"]
    passed = sum(bool(value) for value in gates.values())
    if passed >= 4:
        verdict = "build"
    elif passed >= 2:
        verdict = "observe"
    else:
        verdict = "reject"

    evidence_item_ids = [
        candidate_to_item[candidate_id]
        for candidate_id in raw["evidence_candidate_ids"]
        if candidate_id in candidate_to_item
    ]
    if not evidence_item_ids:
        return None

    product_scores = [
        int(entry["editorial"]["product_value_score"])
        for entry in pool["entries"]
        if entry["candidate"]["candidate_id"] in raw["evidence_candidate_ids"]
    ]
    average_signal = round(sum(product_scores) / len(product_scores)) if product_scores else 0
    score = round((passed / max(1, len(gates))) * 60 + average_signal * 0.4)

    return {
        "title": raw["title"],
        "verdict": verdict,
        "score": min(100, score),
        "target_users": raw["target_users"],
        "pain_point": raw["pain_point"],
        "mvp": raw["mvp"],
        "seven_day_feasibility": bool(raw["seven_day_feasibility"]),
        "payment_signal": raw["payment_signal"],
        "competition_level": raw["competition_level"],
        "hxp_advantage": raw["hxp_advantage"],
        "evidence_item_ids": list(dict.fromkeys(evidence_item_ids)),
    }


def _rejected_candidates(
    pool: Mapping[str, Any],
    scores: Sequence[Mapping[str, Any]],
    selected_candidate_ids: set[str],
) -> list[dict[str, Any]]:
    entries = _index_entries(pool)
    result: list[dict[str, Any]] = []
    for score in scores:
        candidate_id = score["candidate_id"]
        if candidate_id in selected_candidate_ids:
            continue
        entry = entries[candidate_id]
        candidate = entry["candidate"]
        reason = candidate.get("rejection_reason")
        if reason is None:
            reason = REJECTION_REASON_BY_ACTION.get(
                score["recommended_action"], "quota_balance"
            )
        result.append(
            {
                "candidate_id": candidate_id,
                "title": candidate["title_normalized"][:80],
                "rejection_reason": reason,
                "note": "；".join(score["reasons"])[:240],
            }
        )
    return result


def build_briefing(
    pool: Mapping[str, Any],
    score_report: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    entries = _index_entries(pool)
    scores = list(score_report.get("scores", []))
    score_by_id = {score["candidate_id"]: score for score in scores}

    missing = set(entries).difference(score_by_id)
    if missing:
        raise BriefingAssemblyError(f"候选缺少评分：{sorted(missing)}")

    new_scores = _select_new_scores(scores, config)
    continuation_scores = _select_continuation_scores(scores, config)
    selected_scores = [*new_scores, *continuation_scores]

    date_compact = str(pool["date"]).replace("-", "")
    candidate_to_item: dict[str, str] = {}
    for sequence, score in enumerate(selected_scores, start=1):
        candidate_to_item[score["candidate_id"]] = f"item-{date_compact}-{sequence:02d}"

    new_items = [
        _new_item(
            entries[score["candidate_id"]],
            score,
            candidate_to_item[score["candidate_id"]],
            pool["generated_at"],
        )
        for score in new_scores
    ]
    continuation_items = [
        _continuation_item(
            entries[score["candidate_id"]],
            score,
            candidate_to_item[score["candidate_id"]],
            pool["generated_at"],
        )
        for score in continuation_scores
    ]

    selected_entries = [entries[score["candidate_id"]] for score in selected_scores]
    novelty_count = sum(
        score["novelty_kind"] in {"new_theme", "new_angle"} for score in new_scores
    )
    ratio = round(novelty_count / len(new_scores), 4) if new_scores else 0.0
    minimum = int(config["selection"]["target_min_new_items"])
    shortfall_reason = None
    if len(new_items) < minimum:
        shortfall_reason = (
            f"仅有 {len(new_items)} 条候选达到来源、去重与编辑准入线，"
            "未为满足数量目标引入低价值信息。"
        )

    selected_candidate_ids = set(candidate_to_item)
    source_index = sorted(
        {
            source_id
            for entry in selected_entries
            for source_id in entry["candidate"]["source_ids"]
        }
    )

    briefing = {
        "schema_version": "1.0.0",
        "briefing_id": f"hxp-briefing-{pool['date']}",
        "date": pool["date"],
        "timezone": pool.get("timezone", "Asia/Shanghai"),
        "generated_at": pool["generated_at"],
        "language": "zh-CN",
        "title": pool["title"],
        "editorial_policy": {
            "target_min_items": 5,
            "target_max_items": 8,
            "actual_new_item_count": len(new_items),
            "shortfall_reason": shortfall_reason,
            "new_or_new_angle_ratio": ratio,
            "dedup_windows_days": [3, 7, 30],
            "source_requirements_met": _source_requirements_met(
                selected_entries, config
            ),
            "market_session": pool.get("market_session", "not_applicable"),
        },
        "new_items": new_items,
        "continuation_items": continuation_items,
        "content_opportunities": _content_opportunities(pool, candidate_to_item),
        "product_opportunity": _product_opportunity(pool, candidate_to_item),
        "risk_reminder": pool["risk_reminder"],
        "weekly_threads": pool["weekly_threads"],
        "rejected_candidates": _rejected_candidates(
            pool, scores, selected_candidate_ids
        ),
        "source_index": source_index,
    }
    return briefing


def render_markdown(briefing: Mapping[str, Any]) -> str:
    lines = [
        f"# {briefing['title']}",
        "",
        f"> 日期：{briefing['date']}｜时区：{briefing['timezone']}",
        "",
        "## 一、今日新增事实",
        "",
    ]
    for index, item in enumerate(briefing["new_items"], start=1):
        lines.extend(
            [
                f"### {index}. {item['title']}",
                "",
                item["summary"],
                "",
                f"**置信度：** {item['confidence']['level']}。{item['confidence']['rationale']}",
                "",
                "**为什么重要：**",
                *[f"- {value}" for value in item["why_it_matters"]],
                "",
                "**后续关注：**",
                *[f"- {value}" for value in item["follow_up"]],
                "",
                f"**来源 ID：** {', '.join(item['source_ids'])}",
                "",
            ]
        )

    lines.extend(["## 二、延续跟踪", ""])
    if briefing["continuation_items"]:
        for item in briefing["continuation_items"]:
            lines.extend(
                [
                    f"### 【延续跟踪】{item['title']}",
                    "",
                    item["continuation"]["new_delta"],
                    "",
                ]
            )
    else:
        lines.extend(["今日无达到延续跟踪门槛的新增变化。", ""])

    lines.extend(["## 三、今日内容机会", ""])
    for opportunity in briefing["content_opportunities"]:
        lines.extend(
            [
                f"### {opportunity['wechat_title']}",
                f"- 抖音图文：{opportunity['douyin_title']}",
                f"- 角度：{opportunity['angle']}",
                f"- 配图：{opportunity['visual_direction']}",
                "",
            ]
        )

    lines.extend(["## 四、今日产品/项目机会", ""])
    product = briefing.get("product_opportunity")
    if product is None:
        lines.extend(["今日暂无达到产品化门槛的机会。", ""])
    else:
        lines.extend(
            [
                f"### {product['title']}",
                f"- 结论：{product['verdict']}（{product['score']} 分）",
                f"- 面向人群：{'、'.join(product['target_users'])}",
                f"- 痛点：{product['pain_point']}",
                "- MVP：",
                *[f"  - {value}" for value in product["mvp"]],
                "",
            ]
        )

    risk = briefing["risk_reminder"]
    weekly = briefing["weekly_threads"]
    lines.extend(
        [
            "## 五、今日风险提醒",
            "",
            f"### {risk['title']}",
            risk["description"],
            "",
            "## 六、本周累计主线",
            "",
            f"- 关键词：{'、'.join(weekly['keywords'])}",
            f"- 最强趋势：{weekly['strongest_trend']}",
            f"- 深度主题：{weekly['deep_dive_topic']}",
            f"- 产品化机会：{weekly['productization_opportunity']}",
            "",
        ]
    )
    if any(
        item["primary_category"] == "a_share_industry"
        for item in briefing["new_items"]
    ):
        lines.append("> A 股相关内容仅作产业研究与信息整理，不构成投资建议。")
        lines.append("")
    return "\n".join(lines)
