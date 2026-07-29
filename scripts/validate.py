#!/usr/bin/env python3
"""Validate HXP Intelligence Pipeline JSON data.

The validator performs two layers of checks:
1. JSON Schema validation.
2. Cross-field and cross-file semantic validation.

Run all bundled examples:
    python scripts/validate.py --examples

Validate one file:
    python scripts/validate.py --schema schemas/briefing.schema.json \
        --data path/to/briefing.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

ROOT = Path(__file__).resolve().parents[1]

EXAMPLE_PAIRS = (
    (ROOT / "schemas/briefing.schema.json", ROOT / "data/examples/briefing.example.json"),
    (ROOT / "schemas/source.schema.json", ROOT / "data/examples/source.example.json"),
    (ROOT / "schemas/manifest.schema.json", ROOT / "data/examples/manifest.example.json"),
)


class ValidationFailure(Exception):
    """Raised when one or more validation checks fail."""


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise ValidationFailure(f"文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationFailure(
            f"JSON 解析失败：{path}:{exc.lineno}:{exc.colno} {exc.msg}"
        ) from exc


def json_pointer(parts: Iterable[Any]) -> str:
    encoded = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "/" + "/".join(encoded) if encoded else "/"


def validate_schema_document(schema: dict[str, Any], schema_path: Path) -> None:
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValidationFailure(f"Schema 本身无效：{schema_path}\n{exc.message}") from exc


def validate_against_schema(
    schema_path: Path, data_path: Path
) -> tuple[dict[str, Any], Any]:
    schema = load_json(schema_path)
    data = load_json(data_path)

    if not isinstance(schema, dict):
        raise ValidationFailure(f"Schema 根节点必须是对象：{schema_path}")

    validate_schema_document(schema, schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(data), key=lambda error: list(error.absolute_path))

    if errors:
        lines = [f"Schema 校验失败：{data_path}"]
        for error in errors:
            pointer = json_pointer(error.absolute_path)
            lines.append(f"  - {pointer}: {error.message}")
        raise ValidationFailure("\n".join(lines))

    return schema, data


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def unique_values(values: Iterable[str]) -> bool:
    materialized = list(values)
    return len(materialized) == len(set(materialized))


def validate_briefing_semantics(briefing: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    policy = briefing["editorial_policy"]
    new_items = briefing["new_items"]
    continuation_items = briefing["continuation_items"]
    all_items = [*new_items, *continuation_items]

    require(
        policy["actual_new_item_count"] == len(new_items),
        "briefing: editorial_policy.actual_new_item_count 必须等于 new_items 数量",
        errors,
    )

    if len(new_items) < policy["target_min_items"]:
        require(
            bool(policy.get("shortfall_reason")),
            "briefing: 新增事实不足目标数量时必须填写 shortfall_reason",
            errors,
        )

    if len(new_items) >= policy["target_min_items"]:
        require(
            policy["new_or_new_angle_ratio"] >= 0.6,
            "briefing: 正式日报至少 60% 条目必须是新主题或新角度",
            errors,
        )

    item_ids = [item["item_id"] for item in all_items]
    fingerprints = [item["event_fingerprint"] for item in all_items]
    require(unique_values(item_ids), "briefing: item_id 不得重复", errors)
    require(unique_values(fingerprints), "briefing: event_fingerprint 不得重复", errors)

    referenced_source_ids: set[str] = set()
    for item in all_items:
        source_ids = set(item["source_ids"])
        referenced_source_ids.update(source_ids)
        require(
            item["primary_source_id"] in source_ids,
            f"briefing: {item['item_id']} 的 primary_source_id 必须包含在 source_ids 中",
            errors,
        )
        risk_flags = set(item["risk_flags"])
        require(
            not ("none" in risk_flags and len(risk_flags) > 1),
            f"briefing: {item['item_id']} 的 risk_flags 中 none 不能与其他风险并存",
            errors,
        )

    source_index = set(briefing["source_index"])
    require(
        referenced_source_ids.issubset(source_index),
        "briefing: source_index 必须覆盖所有条目引用的 source_ids",
        errors,
    )

    opportunity_ids = [item["opportunity_id"] for item in briefing["content_opportunities"]]
    require(unique_values(opportunity_ids), "briefing: opportunity_id 不得重复", errors)

    valid_item_ids = set(item_ids)
    for opportunity in briefing["content_opportunities"]:
        for related_id in opportunity["related_item_ids"]:
            require(
                related_id in valid_item_ids,
                f"briefing: 内容机会引用了不存在的 item_id：{related_id}",
                errors,
            )

    product = briefing.get("product_opportunity")
    if product is not None:
        if product["verdict"] == "build":
            require(
                product["score"] >= 70,
                "briefing: product_opportunity.verdict=build 时 score 必须至少为 70",
                errors,
            )
            require(
                product["seven_day_feasibility"] is True,
                "briefing: verdict=build 时必须可在 7 天内完成 MVP",
                errors,
            )
        for related_id in product["evidence_item_ids"]:
            require(
                related_id in valid_item_ids,
                f"briefing: 产品机会引用了不存在的 item_id：{related_id}",
                errors,
            )

    return errors


def validate_manifest_semantics(
    manifest: dict[str, Any], briefing: dict[str, Any] | None = None
) -> list[str]:
    errors: list[str] = []
    assets = manifest["assets"]
    summary = manifest["quality_summary"]

    require(
        summary["total_assets"] == len(assets),
        "manifest: quality_summary.total_assets 必须等于 assets 数量",
        errors,
    )
    require(
        summary["passed"]
        == sum(asset["quality_check"]["status"] == "passed" for asset in assets),
        "manifest: quality_summary.passed 与资产状态不一致",
        errors,
    )
    require(
        summary["failed"]
        == sum(asset["quality_check"]["status"] == "failed" for asset in assets),
        "manifest: quality_summary.failed 与资产状态不一致",
        errors,
    )

    require(
        unique_values(asset["asset_id"] for asset in assets),
        "manifest: asset_id 不得重复",
        errors,
    )
    require(
        unique_values(asset["filename"] for asset in assets),
        "manifest: filename 不得重复",
        errors,
    )

    if briefing is not None:
        require(
            manifest["briefing_id"] == briefing["briefing_id"],
            "manifest: briefing_id 必须与 briefing 文件一致",
            errors,
        )
        item_ids = {
            item["item_id"]
            for item in [*briefing["new_items"], *briefing["continuation_items"]]
        }
        for asset in assets:
            if asset["type"] == "summary_poster":
                continue
            require(
                asset["related_item_id"] in item_ids,
                f"manifest: 资产 {asset['asset_id']} 引用了不存在的 item_id",
                errors,
            )

    return errors


def validate_cross_file_examples(
    briefing: dict[str, Any], source: dict[str, Any], manifest: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    require(
        source["source_id"] in set(briefing["source_index"]),
        "examples: source.example.json 的 source_id 未出现在 briefing.source_index",
        errors,
    )
    errors.extend(validate_briefing_semantics(briefing))
    errors.extend(validate_manifest_semantics(manifest, briefing))
    return errors


def validate_examples() -> None:
    loaded: dict[str, Any] = {}
    for schema_path, data_path in EXAMPLE_PAIRS:
        _, data = validate_against_schema(schema_path, data_path)
        loaded[data_path.name] = data
        print(f"PASS schema: {data_path.relative_to(ROOT)}")

    semantic_errors = validate_cross_file_examples(
        loaded["briefing.example.json"],
        loaded["source.example.json"],
        loaded["manifest.example.json"],
    )
    if semantic_errors:
        raise ValidationFailure(
            "语义与跨文件校验失败：\n" + "\n".join(f"  - {item}" for item in semantic_errors)
        )
    print("PASS semantics: examples are internally consistent")


def validate_single(schema_path: Path, data_path: Path) -> None:
    _, data = validate_against_schema(schema_path, data_path)
    name = schema_path.name
    semantic_errors: list[str] = []
    if name == "briefing.schema.json":
        semantic_errors.extend(validate_briefing_semantics(data))
    elif name == "manifest.schema.json":
        semantic_errors.extend(validate_manifest_semantics(data))

    if semantic_errors:
        raise ValidationFailure(
            "语义校验失败：\n" + "\n".join(f"  - {item}" for item in semantic_errors)
        )
    print(f"PASS: {data_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate HXP JSON files")
    parser.add_argument(
        "--examples",
        action="store_true",
        help="validate all bundled example files and cross-file references",
    )
    parser.add_argument("--schema", type=Path, help="path to a JSON Schema")
    parser.add_argument("--data", type=Path, help="path to a JSON data file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.examples or (args.schema is None and args.data is None):
            validate_examples()
        elif args.schema is not None and args.data is not None:
            validate_single(args.schema.resolve(), args.data.resolve())
        else:
            raise ValidationFailure("--schema 与 --data 必须同时提供")
    except ValidationFailure as exc:
        print(f"FAIL\n{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
