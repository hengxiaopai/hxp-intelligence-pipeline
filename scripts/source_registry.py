#!/usr/bin/env python3
"""Validate and inspect the HXP intelligence source registry.

This command does not crawl websites. It validates source policy and emits a
collection plan that a later adapter layer can execute safely.

Examples:
    python scripts/source_registry.py --validate
    python scripts/source_registry.py --list --active-only
    python scripts/source_registry.py --emit-plan --category developer_tools
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "config/sources.json"
DEFAULT_SCHEMA = ROOT / "schemas/source-registry.schema.json"


class RegistryError(Exception):
    """Raised when the registry is structurally or semantically invalid."""


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise RegistryError(f"文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise RegistryError(
            f"JSON 解析失败：{path}:{exc.lineno}:{exc.colno} {exc.msg}"
        ) from exc


def pointer(parts: Iterable[Any]) -> str:
    values = [str(value).replace("~", "~0").replace("/", "~1") for value in parts]
    return "/" + "/".join(values) if values else "/"


def validate_schema(registry: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(registry),
        key=lambda error: [str(value) for value in error.absolute_path],
    )
    return [f"{pointer(error.absolute_path)}: {error.message}" for error in errors]


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate_semantics(registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    sources = registry["sources"]

    ids = [source["registry_id"] for source in sources]
    urls = [source["url"].rstrip("/") for source in sources]
    require(len(ids) == len(set(ids)), "registry_id 不得重复", errors)
    require(len(urls) == len(set(urls)), "来源 URL 不得重复", errors)
    require(any(source["active"] for source in sources), "至少需要一个启用来源", errors)
    require(
        sum(source["authority_level"] == "tier_1_official" for source in sources) >= 3,
        "首批注册表至少需要 3 个 Tier 1 官方来源",
        errors,
    )

    for source in sources:
        source_id = source["registry_id"]
        authority = source["authority_level"]
        scope = source["content_scope"]
        method = source["collection_method"]
        access = source["access_policy"]

        if scope == "platform_rankings":
            require(
                authority == "tier_3_signal_only",
                f"{source_id}: 平台榜单必须标记为 tier_3_signal_only",
                errors,
            )
        if scope == "mixed_official_community":
            require(
                authority != "tier_1_official",
                f"{source_id}: 官方与社区混合内容不能整体标记为 Tier 1",
                errors,
            )
        if scope == "regulatory_filings":
            require(
                source["source_type"] == "financial_filing",
                f"{source_id}: regulatory_filings 必须使用 financial_filing 类型",
                errors,
            )
            require(
                authority == "tier_1_official",
                f"{source_id}: 监管披露来源必须为 Tier 1",
                errors,
            )
        if access == "manual_only":
            require(
                method == "manual_review",
                f"{source_id}: manual_only 必须配合 manual_review",
                errors,
            )
        if access == "official_api_only":
            require(
                method == "api",
                f"{source_id}: official_api_only 必须配合 api",
                errors,
            )
        if authority == "tier_3_signal_only":
            require(
                source["priority"] >= 2,
                f"{source_id}: Tier 3 信号源不得设置为最高优先级 1",
                errors,
            )
        require(
            not (
                "community" in source["tags"]
                and authority == "tier_1_official"
            ),
            f"{source_id}: 社区内容不得默认标记为 Tier 1",
            errors,
        )

    return errors


def select_sources(
    registry: dict[str, Any],
    *,
    category: str | None,
    active_only: bool,
    max_priority: int | None,
) -> list[dict[str, Any]]:
    sources = registry["sources"]
    selected: list[dict[str, Any]] = []
    for source in sources:
        if category and source["primary_category"] != category:
            continue
        if active_only and not source["active"]:
            continue
        if max_priority is not None and source["priority"] > max_priority:
            continue
        selected.append(source)
    return sorted(selected, key=lambda item: (item["priority"], item["name"]))


def emit_table(sources: list[dict[str, Any]]) -> None:
    print("priority  authority          method         category           source")
    print("--------  -----------------  -------------  -----------------  ------------------------------")
    for source in sources:
        print(
            f"{source['priority']:<8}  "
            f"{source['authority_level']:<17}  "
            f"{source['collection_method']:<13}  "
            f"{source['primary_category']:<17}  "
            f"{source['registry_id']}"
        )


def emit_plan(sources: list[dict[str, Any]]) -> None:
    plan = {
        "plan_version": "1.0.0",
        "source_count": len(sources),
        "sources": [
            {
                "registry_id": source["registry_id"],
                "url": source["url"],
                "priority": source["priority"],
                "collection_method": source["collection_method"],
                "max_age_hours": source["max_age_hours"],
                "min_interval_minutes": source["min_interval_minutes"],
                "parser_hint": source["parser_hint"],
                "access_policy": source["access_policy"],
            }
            for source in sources
        ],
    }
    print(json.dumps(plan, ensure_ascii=False, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate and inspect source registry")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--emit-plan", action="store_true")
    parser.add_argument("--category")
    parser.add_argument("--active-only", action="store_true")
    parser.add_argument("--max-priority", type=int, choices=range(1, 6))
    parser.add_argument("--json", action="store_true", help="print selected sources as JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        registry = load_json(args.registry.resolve())
        schema = load_json(args.schema.resolve())
        if not isinstance(registry, dict) or not isinstance(schema, dict):
            raise RegistryError("注册表与 Schema 根节点必须是 JSON 对象")

        schema_errors = validate_schema(registry, schema)
        semantic_errors = validate_semantics(registry) if not schema_errors else []
        errors = [*schema_errors, *semantic_errors]
        if errors:
            raise RegistryError("\n".join(f"- {error}" for error in errors))

        selected = select_sources(
            registry,
            category=args.category,
            active_only=args.active_only,
            max_priority=args.max_priority,
        )

        if args.validate or not any((args.list, args.emit_plan, args.json)):
            print(f"PASS: {args.registry} ({len(registry['sources'])} sources)")
        if args.list:
            emit_table(selected)
        if args.emit_plan:
            emit_plan(selected)
        if args.json:
            print(json.dumps(selected, ensure_ascii=False, indent=2))
    except RegistryError as exc:
        print(f"FAIL\n{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
