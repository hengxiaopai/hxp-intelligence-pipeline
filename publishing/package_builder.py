"""Build deterministic draft packages from an approved briefing and export manifest."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .platform_rules import (
    aggregate_risk_flags,
    canonical_hash,
    profile_map,
    truncate_units,
    validate_platform_package,
)


class ContentPackageError(ValueError):
    """Raised when source content or platform assets are incomplete or unsafe."""


CATEGORY_TAGS = {
    "career_skills": "#未来工作",
    "developer_tools": "#AI编程",
    "business_strategy": "#企业AI",
    "risk_counter_signal": "#网络安全",
    "ai_technology": "#人工智能",
    "open_source_projects": "#开源项目",
    "a_share_market": "#A股观察",
}


def _source_map(sources: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for source in sources:
        source_id = str(source["source_id"])
        publisher = str(source.get("publisher", "")).strip()
        if not publisher:
            raise ContentPackageError(f"来源缺少发布方：{source_id}")
        if source_id in result:
            raise ContentPackageError(f"来源ID重复：{source_id}")
        result[source_id] = publisher
    return result


def load_sources(source_dir: Path) -> list[dict[str, Any]]:
    import json

    values: list[dict[str, Any]] = []
    for path in sorted(source_dir.glob("*.json")):
        values.append(json.loads(path.read_text(encoding="utf-8")))
    if not values:
        raise ContentPackageError(f"来源目录为空：{source_dir}")
    return values


def _items(briefing: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    values = [
        *briefing.get("new_items", []),
        *briefing.get("continuation_items", []),
    ]
    if not values:
        raise ContentPackageError("简报没有正式入选条目")
    return values


def _publishers_for_items(
    items: Sequence[Mapping[str, Any]],
    publishers: Mapping[str, str],
) -> list[str]:
    values: list[str] = []
    for item in items:
        for source_id in item.get("source_ids", []):
            if source_id not in publishers:
                raise ContentPackageError(
                    f"正式条目引用未知来源：{item['item_id']}：{source_id}"
                )
            values.append(publishers[source_id])
    return list(dict.fromkeys(values))


def _ordered_exports(export_manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    values = list(export_manifest.get("exports", []))
    if not values:
        raise ContentPackageError("Export Manifest没有可用资产")
    for export in values:
        if export.get("status") != "passed":
            raise ContentPackageError(f"平台资产未通过：{export.get('export_id')}")
        if export.get("text_overflow") is not False:
            raise ContentPackageError(f"平台资产存在文本溢出：{export.get('export_id')}")
        if export.get("crop_safe") is not True:
            raise ContentPackageError(f"平台资产裁切不安全：{export.get('export_id')}")
        if not export.get("png") or not export["png"].get("sha256"):
            raise ContentPackageError(f"平台资产缺少PNG记录：{export.get('export_id')}")
    return sorted(
        values,
        key=lambda value: (
            str(value["preset"]),
            int(str(value["job_id"]).rsplit("-", 1)[-1]),
        ),
    )


def _assets_for_platform(
    *,
    platform: str,
    preset: str,
    exports: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    matching = [value for value in exports if value["preset"] == preset]
    if not matching:
        raise ContentPackageError(f"平台缺少预设资产：{platform}：{preset}")
    details = [value for value in matching if value.get("item_id")]
    summary = [value for value in matching if value.get("item_id") is None]

    if platform in {"wechat", "x"}:
        selected = summary[:1]
    elif platform in {"xiaohongshu", "douyin"}:
        selected = [*summary[:1], *details]
    else:
        selected = [*summary[:1], *details]
    if not selected:
        selected = details[:1]
    assets: list[dict[str, Any]] = []
    for order, export in enumerate(selected, start=1):
        png = export["png"]
        assets.append(
            {
                "export_id": export["export_id"],
                "preset": export["preset"],
                "order": order,
                "path": png["path"],
                "sha256": png["sha256"],
                "width": int(export["width"]),
                "height": int(export["height"]),
            }
        )
    return assets


def _date_label(date: str) -> str:
    return date.replace("-", ".")


def _slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return text[:120] if len(text) >= 3 else "hxp-daily-intelligence"


def _hashtags(items: Sequence[Mapping[str, Any]], maximum: int) -> list[str]:
    values = ["#珩小派", "#AI情报", "#一人公司"]
    for item in items:
        tag = CATEGORY_TAGS.get(str(item.get("primary_category", "")))
        if tag:
            values.append(tag)
    return list(dict.fromkeys(values))[:maximum]


def _source_line(item: Mapping[str, Any], publishers: Mapping[str, str]) -> str:
    labels = [publishers[value] for value in item.get("source_ids", [])]
    return " / ".join(dict.fromkeys(labels))


def _long_body(
    briefing: Mapping[str, Any],
    items: Sequence[Mapping[str, Any]],
    publishers: Mapping[str, str],
) -> str:
    weekly = briefing.get("weekly_threads", {})
    lines = [
        f"# {briefing['title']}",
        "",
        "## 今日判断",
        "",
        str(weekly.get("strongest_trend", items[0]["summary"])),
        "",
    ]
    for index, item in enumerate(items, start=1):
        lines.extend(
            [
                f"## {index:02d}｜{item['title']}",
                "",
                f"**{item.get('subtitle', '')}**" if item.get("subtitle") else "",
                "",
                str(item["summary"]),
                "",
                "**为什么重要**",
                *[f"- {value}" for value in item.get("why_it_matters", [])],
                "",
                "**后续关注**",
                *[f"- {value}" for value in item.get("follow_up", [])],
                "",
                f"来源：{_source_line(item, publishers)}",
                "",
            ]
        )
    source_labels = _publishers_for_items(items, publishers)
    lines.extend(
        [
            "## 来源",
            "",
            *[f"- {value}" for value in source_labels],
            "",
            "珩小派｜一人公司情报雷达",
        ]
    )
    return "\n".join(value for value in lines if value is not None).strip() + "\n"


def _daily_caption(
    items: Sequence[Mapping[str, Any]],
    *,
    intro: str,
    publishers: Mapping[str, str],
    include_sources: bool = True,
) -> str:
    lines = [intro, ""]
    for index, item in enumerate(items, start=1):
        lines.append(f"{index}. {item['title']}｜{item['summary']}")
    if include_sources:
        lines.extend(
            [
                "",
                "来源：" + " / ".join(_publishers_for_items(items, publishers)),
            ]
        )
    return "\n".join(lines).strip()


def _x_thread(
    items: Sequence[Mapping[str, Any]],
    publishers: Mapping[str, str],
) -> list[str]:
    values: list[str] = []
    total = len(items)
    for index, item in enumerate(items, start=1):
        source = _source_line(item, publishers)
        text = f"{index}/{total} {item['title']}：{item['summary']} 来源：{source}"
        values.append(truncate_units(text, 280))
    return values[:8]


def _content_for_platform(
    *,
    platform: str,
    briefing: Mapping[str, Any],
    items: Sequence[Mapping[str, Any]],
    publishers: Mapping[str, str],
    profile: Mapping[str, Any],
    investment_related: bool,
) -> dict[str, Any]:
    date = _date_label(str(briefing["date"]))
    total = len(items)
    first = items[0]
    sources = _publishers_for_items(items, publishers)
    body = _long_body(briefing, items, publishers)
    risk_disclaimer = "本文仅作信息整理与研究交流，不构成投资建议。" if investment_related else None

    if platform == "wechat":
        title = truncate_units(f"{first['title']}｜今日{total}条多元情报", int(profile["title_max_units"]))
        summary = truncate_units(
            str(briefing.get("weekly_threads", {}).get("strongest_trend", first["summary"])),
            int(profile["summary_max_units"]),
        )
        return {
            "title": title,
            "summary": summary,
            "body_markdown": body + (("\n> " + risk_disclaimer + "\n") if risk_disclaimer else ""),
            "caption": "",
            "thread": [],
            "hashtags": [],
            "seo_title": "",
            "seo_description": "",
            "slug": "hxp-daily-intelligence",
            "source_labels": sources,
            "risk_disclaimer": risk_disclaimer,
        }

    if platform == "xiaohongshu":
        title = truncate_units(f"今日{total}条AI情报｜{first['title']}", int(profile["title_max_units"]))
        caption = _daily_caption(
            items,
            intro=f"{date} 珩小派多元情报。今天最值得关注的是：{first['summary']}",
            publishers=publishers,
        )
        if risk_disclaimer:
            caption += "\n\n" + risk_disclaimer
        return {
            "title": title,
            "summary": "",
            "body_markdown": "",
            "caption": truncate_units(caption, int(profile["body_max_units"])),
            "thread": [],
            "hashtags": _hashtags(items, int(profile["hashtags_max_items"])),
            "seo_title": "",
            "seo_description": "",
            "slug": "hxp-daily-intelligence",
            "source_labels": sources,
            "risk_disclaimer": risk_disclaimer,
        }

    if platform == "douyin":
        title = truncate_units(f"今天这{total}条AI变化值得看", int(profile["title_max_units"]))
        caption = _daily_caption(
            items,
            intro=f"珩小派多元情报｜{date}\n从岗位跨界到Agent治理，今天的变化都在指向同一件事：AI正在进入可执行、可审计阶段。",
            publishers=publishers,
        )
        if risk_disclaimer:
            caption += "\n\n" + risk_disclaimer
        return {
            "title": title,
            "summary": "",
            "body_markdown": "",
            "caption": truncate_units(caption, int(profile["body_max_units"])),
            "thread": [],
            "hashtags": _hashtags(items, int(profile["hashtags_max_items"])),
            "seo_title": "",
            "seo_description": "",
            "slug": "hxp-daily-intelligence",
            "source_labels": sources,
            "risk_disclaimer": risk_disclaimer,
        }

    if platform == "x":
        caption = truncate_units(
            f"{date} 珩小派多元情报：{first['title']}。{first['summary']} 今日共{total}条，详见线程。 来源：{' / '.join(sources)}",
            int(profile["body_max_units"]),
        )
        return {
            "title": "",
            "summary": "",
            "body_markdown": "",
            "caption": caption,
            "thread": _x_thread(items, publishers),
            "hashtags": _hashtags(items, int(profile["hashtags_max_items"])),
            "seo_title": "",
            "seo_description": "",
            "slug": "hxp-daily-intelligence",
            "source_labels": sources,
            "risk_disclaimer": risk_disclaimer,
        }

    title = truncate_units(f"{briefing['title']}｜{total}条今日焦点", int(profile["title_max_units"]))
    summary = truncate_units(
        str(briefing.get("weekly_threads", {}).get("strongest_trend", first["summary"])),
        int(profile["summary_max_units"]),
    )
    return {
        "title": title,
        "summary": summary,
        "body_markdown": body + (("\n> " + risk_disclaimer + "\n") if risk_disclaimer else ""),
        "caption": "",
        "thread": [],
        "hashtags": [],
        "seo_title": truncate_units(title, 100),
        "seo_description": truncate_units(summary, 300),
        "slug": _slug(f"hxp-intelligence-{briefing['date']}"),
        "source_labels": sources,
        "risk_disclaimer": risk_disclaimer,
    }


def build_content_package_batch(
    *,
    briefing: Mapping[str, Any],
    export_manifest: Mapping[str, Any],
    sources: Sequence[Mapping[str, Any]],
    profiles: Mapping[str, Any],
) -> dict[str, Any]:
    """Build exactly five offline platform packages with stable hashes."""
    if briefing.get("date") != export_manifest.get("date"):
        raise ContentPackageError("简报与Export Manifest日期不一致")
    compact = str(briefing["date"]).replace("-", "")
    if export_manifest.get("export_manifest_id") != f"export-manifest-{compact}":
        raise ContentPackageError("Export Manifest ID与简报日期不一致")
    items = _items(briefing)
    publishers = _source_map(sources)
    exports = _ordered_exports(export_manifest)
    platform_profiles = profile_map(profiles)
    investment_related = "investment_expression" in aggregate_risk_flags(items)

    packages: list[dict[str, Any]] = []
    for platform in ("wechat", "xiaohongshu", "douyin", "x", "website"):
        profile = platform_profiles[platform]
        assets = _assets_for_platform(
            platform=platform,
            preset=str(profile["required_preset"]),
            exports=exports,
        )
        content = _content_for_platform(
            platform=platform,
            briefing=briefing,
            items=items,
            publishers=publishers,
            profile=profile,
            investment_related=investment_related,
        )
        package = {
            "package_id": f"content-package-{compact}-{platform}",
            "platform": platform,
            "status": "draft",
            "content_hash": canonical_hash({"content": content, "assets": assets}),
            "content": content,
            "assets": assets,
            "dependencies": {
                "briefing_id": briefing["briefing_id"],
                "export_manifest_id": export_manifest["export_manifest_id"],
            },
            "risk_flags": aggregate_risk_flags(items),
            "validations": {},
        }
        validations = validate_platform_package(package, profile)
        package["validations"] = validations
        package["status"] = "validated" if all(validations.values()) else "blocked"
        packages.append(package)

    blocked = sum(value["status"] == "blocked" for value in packages)
    return {
        "schema_version": "1.0.0",
        "package_batch_id": f"content-package-batch-{compact}",
        "briefing_id": briefing["briefing_id"],
        "export_manifest_id": export_manifest["export_manifest_id"],
        "date": briefing["date"],
        "generated_at": briefing["generated_at"],
        "language": "zh-CN",
        "write_actions_enabled": False,
        "packages": packages,
        "summary": {
            "total": len(packages),
            "validated": len(packages) - blocked,
            "blocked": blocked,
            "platform_counts": {
                platform: sum(value["platform"] == platform for value in packages)
                for platform in ("wechat", "xiaohongshu", "douyin", "x", "website")
            },
        },
    }
