#!/usr/bin/env python3
"""Validate multi-platform export files, hashes, dimensions and approval gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from visual.queue import load_json  # noqa: E402
from visual.rasterizer import RasterizationError, validate_png  # noqa: E402


class PlatformExportValidationError(ValueError):
    """Raised when platform exports are not safe to publish."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    return parser.parse_args()


def _schema_errors(value: Any) -> list[str]:
    schema = load_json(ROOT / "schemas/export-manifest.schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(
            validator.iter_errors(value),
            key=lambda error: [str(part) for part in error.absolute_path],
        )
    ]


def _resolve(value: str, manifest_path: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    repository = ROOT / path
    if repository.exists():
        return repository
    return manifest_path.parent / path


def _validate_file(record: dict[str, Any], manifest_path: Path) -> Path:
    path = _resolve(record["path"], manifest_path)
    if not path.is_file():
        raise PlatformExportValidationError(f"导出文件不存在：{path}")
    body = path.read_bytes()
    if hashlib.sha256(body).hexdigest() != record["sha256"]:
        raise PlatformExportValidationError(f"导出文件SHA-256不一致：{path}")
    if len(body) != int(record["byte_size"]):
        raise PlatformExportValidationError(f"导出文件字节数不一致：{path}")
    return path


def validate(manifest_path: Path) -> None:
    manifest = load_json(manifest_path)
    errors = _schema_errors(manifest)
    if errors:
        raise PlatformExportValidationError("Schema校验失败：\n- " + "\n- ".join(errors))

    exports = manifest["exports"]
    identifiers = [value["export_id"] for value in exports]
    if len(identifiers) != len(set(identifiers)):
        raise PlatformExportValidationError("多平台导出ID重复")

    for export in exports:
        if export["status"] != "passed":
            raise PlatformExportValidationError(
                f"多平台导出未通过：{export['export_id']}：{'; '.join(export['errors'])}"
            )
        if export["text_overflow"]:
            raise PlatformExportValidationError(f"多平台导出存在文字溢出：{export['export_id']}")
        if not export["crop_safe"]:
            raise PlatformExportValidationError(f"多平台导出裁切不安全：{export['export_id']}")
        if export["item_id"] is not None:
            if export["review_decision"] != "approved":
                raise PlatformExportValidationError(f"详情图未经人工批准：{export['export_id']}")
            if not export["source_request_id"] or not export["source_asset_sha256"]:
                raise PlatformExportValidationError(f"详情图缺少主视觉审计引用：{export['export_id']}")
        else:
            if export["review_decision"] != "not_applicable":
                raise PlatformExportValidationError(f"总览图审核状态无效：{export['export_id']}")

        svg_path = _validate_file(export["svg"], manifest_path)
        png_path = _validate_file(export["png"], manifest_path)
        svg_text = svg_path.read_text(encoding="utf-8")
        expected = f'width="{export["width"]}" height="{export["height"]}"'
        if expected not in svg_text:
            raise PlatformExportValidationError(
                f"SVG画布尺寸不正确：{export['export_id']}，应包含 {expected}"
            )
        validate_png(
            png_path,
            width=int(export["width"]),
            height=int(export["height"]),
        )

    summary = manifest["summary"]
    expected_total = len(exports)
    expected_passed = sum(value["status"] == "passed" for value in exports)
    expected_failed = expected_total - expected_passed
    if summary["total"] != expected_total:
        raise PlatformExportValidationError("Manifest total统计不一致")
    if summary["passed"] != expected_passed:
        raise PlatformExportValidationError("Manifest passed统计不一致")
    if summary["failed"] != expected_failed:
        raise PlatformExportValidationError("Manifest failed统计不一致")

    for preset, count in summary["preset_counts"].items():
        actual = sum(value["preset"] == preset for value in exports)
        if count != actual:
            raise PlatformExportValidationError(f"Manifest预设统计不一致：{preset}")


def main() -> int:
    args = parse_args()
    try:
        validate(args.manifest)
    except (
        PlatformExportValidationError,
        RasterizationError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"PASS platform exports: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
