"""Build a deterministic visual queue from one approved daily run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


class VisualQueueError(ValueError):
    """Raised when an unapproved or incomplete run requests visual production."""


INFORMATION_LABELS = {
    "official_release": "新发布",
    "paper": "论文",
    "rumor": "传闻",
    "research_report": "研究报告",
    "financial_report": "财报",
    "earnings_guidance": "业绩预告",
    "social_trend": "社媒热点",
    "github_project": "GitHub项目",
    "github_update": "GitHub更新",
    "policy": "政策",
    "funding": "融资",
    "company_announcement": "公告",
    "product_launch": "产品发布",
    "security_incident": "安全事件",
    "market_flow": "资金动向",
    "design_reference": "设计灵感",
}

CONFIDENCE_LABELS = {
    "high": "高",
    "medium_high": "中高",
    "observe": "观察",
    "low": "低",
}

CONVERSION_LABELS = {
    "wechat_article": "公众号",
    "douyin_carousel": "抖音图文",
    "short_video": "视频",
    "poster": "海报",
    "product_prototype": "产品原型",
    "deep_report": "深度报告",
    "industry_observation": "投资观察",
    "design_inspiration": "设计灵感",
    "database_update": "数据库更新",
    "website_feature": "网站专题",
}

SUPPORTED_VISUAL_SUFFIXES = (".png", ".jpg", ".jpeg", ".svg")


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise VisualQueueError(f"文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise VisualQueueError(
            f"JSON无效：{path}:{exc.lineno}:{exc.colno}"
        ) from exc


def _path_label(path: Path) -> str:
    resolved = path.resolve()
    repository_root = Path(__file__).resolve().parents[1]
    try:
        return resolved.relative_to(repository_root).as_posix()
    except ValueError:
        return resolved.as_posix()


def resolve_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[1] / path


def _assert_run_approved(run: Mapping[str, Any]) -> None:
    if run.get("status") != "validated":
        raise VisualQueueError("只有status=validated的运行可以进入视觉队列")
    if run.get("review_status") != "approved":
        raise VisualQueueError("只有人工审核approved的运行可以进入视觉队列")
    if run.get("publication_allowed") is not True:
        raise VisualQueueError("publication_allowed=false，禁止创建正式视觉队列")
    failed = sorted(
        key for key, value in run.get("validations", {}).items() if value is not True
    )
    if failed:
        raise VisualQueueError(f"运行仍有未通过验证：{failed}")


def _source_publishers(run_dir: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted((run_dir / "sources").glob("*.json")):
        source = load_json(path)
        source_id = source["source_id"]
        if source_id in result:
            raise VisualQueueError(f"来源ID重复：{source_id}")
        result[source_id] = source["publisher"]
    if not result:
        raise VisualQueueError("视觉队列需要可追溯的来源记录")
    return result


def _find_visual(visual_dir: Path | None, item_id: str) -> Path | None:
    if visual_dir is None:
        return None
    for suffix in SUPPORTED_VISUAL_SUFFIXES:
        path = visual_dir / f"{item_id}{suffix}"
        if path.is_file():
            return path
    return None


def _format_date(value: str) -> str:
    year, month, day = value.split("-")
    return f"{year}.{month}.{day}"


def _labels(values: list[str], mapping: Mapping[str, str]) -> str:
    labels = [mapping.get(value, value) for value in values]
    return " / ".join(dict.fromkeys(labels))


def _detail_content(
    *,
    item: Mapping[str, Any],
    index: int,
    total: int,
    date: str,
    publishers: Mapping[str, str],
) -> dict[str, Any]:
    source_labels = [
        publishers[source_id]
        for source_id in item["source_ids"]
        if source_id in publishers
    ]
    if not source_labels:
        raise VisualQueueError(f"条目缺少来源简称：{item['item_id']}")
    conversion = _labels(item["conversion_directions"], CONVERSION_LABELS)
    confidence = item["confidence"]
    confidence_label = CONFIDENCE_LABELS.get(
        confidence["level"], confidence["level"]
    )
    return {
        "eyebrow": f"珩小派多元情报｜今日焦点 {index:02d}",
        "title": item["title"],
        "subtitle": item.get("subtitle", ""),
        "date_label": _format_date(date),
        "index_label": f"{index:02d} / {total:02d}",
        "summary": item["summary"],
        "information_label": "信息类型："
        + _labels(item["information_types"], INFORMATION_LABELS),
        "confidence_label": f"置信度：{confidence_label}｜{confidence['rationale']}",
        "why_it_matters": item["why_it_matters"],
        "follow_up": item["follow_up"],
        "conversion_label": "可转化方向：" + conversion,
        "source_labels": list(dict.fromkeys(source_labels)),
        "focus_titles": [],
        "main_threads": [],
        "content_opportunities": [],
        "product_opportunity": None,
        "risk_reminder": None,
    }


def _summary_content(briefing: Mapping[str, Any], total: int) -> dict[str, Any]:
    weekly = briefing["weekly_threads"]
    product = briefing.get("product_opportunity")
    risk = briefing.get("risk_reminder")
    focus_items = [
        *briefing.get("new_items", []),
        *briefing.get("continuation_items", []),
    ]
    return {
        "eyebrow": "珩小派多元情报｜今日总览",
        "title": f"{briefing['date'][5:].replace('-', '.')} 情报总览",
        "subtitle": f"今日 {total} 大焦点 + 主线判断",
        "date_label": _format_date(briefing["date"]),
        "index_label": "OVERVIEW",
        "summary": weekly["strongest_trend"],
        "information_label": "",
        "confidence_label": "",
        "why_it_matters": [],
        "follow_up": [],
        "conversion_label": "珩小派｜一人公司情报雷达",
        "source_labels": [],
        "focus_titles": [item["title"] for item in focus_items],
        "main_threads": [
            weekly["strongest_trend"],
            "最值得深挖：" + weekly["deep_dive_topic"],
            "产品化主线：" + weekly["productization_opportunity"],
        ],
        "content_opportunities": [
            opportunity["wechat_title"]
            for opportunity in briefing["content_opportunities"]
        ],
        "product_opportunity": product["title"] if product else None,
        "risk_reminder": risk["title"] if risk else None,
    }


def build_visual_queue(
    *,
    run_dir: Path,
    logo_path: Path,
    theme: Mapping[str, Any],
    visual_dir: Path | None = None,
    allow_placeholder: bool = False,
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    run = load_json(run_dir / "run.json")
    _assert_run_approved(run)
    briefing = load_json(run_dir / "briefing.json")
    if briefing["date"] != run["date"]:
        raise VisualQueueError("briefing与run日期不一致")
    if not logo_path.is_file():
        raise VisualQueueError(
            f"缺少已批准品牌Logo：{logo_path}。仓库不会自动伪造Logo。"
        )

    publishers = _source_publishers(run_dir)
    items = [
        *briefing.get("new_items", []),
        *briefing.get("continuation_items", []),
    ]
    if not items:
        raise VisualQueueError("简报没有可生成海报的正式条目")

    compact = briefing["date"].replace("-", "")
    jobs: list[dict[str, Any]] = []
    missing_visuals = 0
    for index, item in enumerate(items, start=1):
        visual = _find_visual(visual_dir, item["item_id"])
        if visual is None:
            missing_visuals += 1
        jobs.append(
            {
                "job_id": f"visual-job-{compact}-{index:02d}",
                "order": index,
                "kind": "detail_9x16",
                "item_id": item["item_id"],
                "status": (
                    "ready_to_render"
                    if visual is not None or allow_placeholder
                    else "waiting_visual"
                ),
                "output_base": f"poster-{index:02d}-{item['item_id']}",
                "visual_asset_path": _path_label(visual) if visual else None,
                "visual_brief": {
                    "concept": item["visual_brief"]["concept"],
                    "must_not_fabricate": item["visual_brief"].get(
                        "must_not_fabricate", []
                    ),
                },
                "content": _detail_content(
                    item=item,
                    index=index,
                    total=len(items),
                    date=briefing["date"],
                    publishers=publishers,
                ),
            }
        )

    summary_index = len(jobs) + 1
    jobs.append(
        {
            "job_id": f"visual-job-{compact}-{summary_index:02d}",
            "order": summary_index,
            "kind": "summary_9x16",
            "item_id": None,
            "status": "ready_to_render",
            "output_base": f"poster-{summary_index:02d}-summary",
            "visual_asset_path": None,
            "visual_brief": {
                "concept": "以编辑式数据看板汇总今日焦点、主线、内容机会、产品机会与风险提醒",
                "must_not_fabricate": [
                    "不得新增简报中不存在的焦点",
                    "不得把内部淘汰候选放入总览",
                ],
            },
            "content": _summary_content(briefing, len(items)),
        }
    )

    preview_only = bool(missing_visuals and allow_placeholder)
    return {
        "schema_version": "1.0.0",
        "queue_id": f"visual-queue-{compact}",
        "briefing_id": briefing["briefing_id"],
        "date": briefing["date"],
        "generated_at": run["generated_at"],
        "template_version": theme["version"],
        "canvas": theme["canvas"],
        "preview_only": preview_only,
        "logo_path": _path_label(logo_path),
        "asset_policy": {
            "logo_required": True,
            "detail_visual_required": True,
            "allow_placeholder": bool(allow_placeholder),
        },
        "jobs": jobs,
    }
