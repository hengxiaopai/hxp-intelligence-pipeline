"""Deterministic text, risk and safety rules for offline platform packages."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from visual.layout import display_units


SENSITIVE_PATTERNS = (
    re.compile(r"(?i)authorization\s*[:=]"),
    re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)(api[_ -]?key|token|password|cookie|session)\s*[:=]\s*\S+"),
    re.compile(r"https?://[^\s/@:]+:[^\s/@]+@"),
)

ABSOLUTE_OR_RETURN_PATTERNS = (
    re.compile(r"稳赚|保证收益|必涨|零风险|绝对安全|百分百|100%获利"),
)

INVESTMENT_KEYWORDS = (
    "A股",
    "股票",
    "个股",
    "涨停",
    "投资建议",
    "资金流",
    "买入",
    "卖出",
)

RISK_MAP = {
    "security_sensitive": "security",
    "security": "security",
    "policy_sensitive": "policy_sensitivity",
    "policy_sensitivity": "policy_sensitivity",
    "unconfirmed": "unconfirmed_claim",
    "rumor": "unconfirmed_claim",
    "copyright": "copyright",
    "platform_review": "platform_review",
}

PLATFORMS = {"wechat", "xiaohongshu", "douyin", "x", "website", "zhihu"}


def canonical_hash(value: Any) -> str:
    body = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def truncate_units(value: str, maximum_units: int) -> str:
    text = str(value).strip()
    if maximum_units <= 0 or display_units(text) <= maximum_units:
        return text
    output: list[str] = []
    used = 0
    budget = max(1, maximum_units - 2)
    for character in text:
        width = display_units(character)
        if used + width > budget:
            break
        output.append(character)
        used += width
    return "".join(output).rstrip() + "…"


def contains_sensitive_data(text: str) -> bool:
    return any(pattern.search(str(text)) for pattern in SENSITIVE_PATTERNS)


def contains_absolute_or_return_claim(text: str) -> bool:
    return any(pattern.search(str(text)) for pattern in ABSOLUTE_OR_RETURN_PATTERNS)


def is_investment_related(items: Sequence[Mapping[str, Any]]) -> bool:
    joined = "\n".join(
        str(value)
        for item in items
        for value in (
            item.get("title", ""),
            item.get("subtitle", ""),
            item.get("summary", ""),
            item.get("primary_category", ""),
        )
    )
    categories = {str(item.get("primary_category", "")) for item in items}
    if categories.intersection({"a_share_market", "finance_investment", "market_flow"}):
        return True
    return any(keyword in joined for keyword in INVESTMENT_KEYWORDS)


def aggregate_risk_flags(items: Sequence[Mapping[str, Any]]) -> list[str]:
    risks: set[str] = set()
    if is_investment_related(items):
        risks.add("investment_expression")
    for item in items:
        information_types = {str(value) for value in item.get("information_types", [])}
        if "rumor" in information_types:
            risks.add("unconfirmed_claim")
        for raw in item.get("risk_flags", []):
            value = str(raw)
            if value == "none":
                continue
            risks.add(RISK_MAP.get(value, "platform_review"))
    return sorted(risks) if risks else ["none"]


def profile_map(profiles: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for profile in profiles.get("platforms", []):
        platform = str(profile["platform"])
        if platform in result:
            raise ValueError(f"平台配置重复：{platform}")
        result[platform] = profile
    if set(result) != PLATFORMS:
        raise ValueError(f"平台配置必须完整覆盖：{sorted(PLATFORMS)}")
    if profiles.get("write_actions_enabled") is not False:
        raise ValueError("发布准备必须保持 write_actions_enabled=false")
    return result


def _field_present(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return value is not None


def validate_platform_package(
    package: Mapping[str, Any],
    profile: Mapping[str, Any],
) -> dict[str, bool]:
    content = package["content"]
    assets = package["assets"]
    required_fields = [str(value) for value in profile.get("required_fields", [])]
    required_present = all(_field_present(content.get(field)) for field in required_fields)

    title_limit = int(profile.get("title_max_units", 0))
    summary_limit = int(profile.get("summary_max_units", 0))
    body_limit = int(profile.get("body_max_units", 0))
    platform = str(package["platform"])
    body_value = (
        content.get("caption", "")
        if platform in {"xiaohongshu", "douyin", "x"}
        else content.get("body_markdown", "")
    )
    length_ok = all(
        limit <= 0 or display_units(str(value)) <= limit
        for value, limit in (
            (content.get("title", ""), title_limit),
            (content.get("summary", ""), summary_limit),
            (body_value, body_limit),
        )
    )
    if platform == "zhihu":
        length_ok = length_ok and display_units(str(content.get("answer_markdown", ""))) <= body_limit

    collection_limits_ok = (
        len(content.get("hashtags", [])) <= int(profile.get("hashtags_max_items", 0))
        and len(content.get("thread", [])) <= int(profile.get("thread_max_items", 0))
    )
    preset = str(profile["required_preset"])
    assets_ok = bool(assets) and all(
        asset.get("preset") == preset
        and bool(asset.get("path"))
        and bool(asset.get("sha256"))
        for asset in assets
    )
    sources_ok = bool(content.get("source_labels"))
    risk_flags = set(package.get("risk_flags", []))
    disclaimer_required = "investment_expression" in risk_flags
    disclaimer_ok = not disclaimer_required or (
        isinstance(content.get("risk_disclaimer"), str)
        and "不构成投资建议" in content["risk_disclaimer"]
    )
    all_text = "\n".join(
        [
            str(content.get("title", "")),
            str(content.get("summary", "")),
            str(content.get("body_markdown", "")),
            str(content.get("caption", "")),
            str(content.get("answer_question_placeholder", "")),
            str(content.get("answer_markdown", "")),
            *[str(value) for value in content.get("thread", [])],
        ]
    )
    safety_ok = not contains_sensitive_data(all_text)
    platform_claims_ok = not contains_absolute_or_return_claim(all_text)
    return {
        "platform_profile_passed": bool(
            required_present and length_ok and collection_limits_ok and platform_claims_ok
        ),
        "assets_verified": assets_ok,
        "sources_present": sources_ok,
        "internal_content_absent": "rejected_candidates" not in all_text
        and "内部淘汰" not in all_text,
        "sensitive_data_absent": safety_ok,
        "disclaimer_present_when_required": disclaimer_ok,
    }
