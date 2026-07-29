#!/usr/bin/env python3
"""Validate visual queue/manifest references, hashes, dimensions and release gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from visual.queue import load_json  # noqa: E402
from visual.rasterizer import RasterizationError, validate_png  # noqa: E402


class VisualValidationError(ValueError):
    """Raised when generated visual assets are not safe to publish."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    return parser.parse_args()


def _schema_errors(schema_path: Path, value: Any) -> list[str]:
    schema = load_json(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(
            validator.iter_errors(value),
            key=lambda error: [str(part) for part in error.absolute_path],
        )
    ]


def _resolve_record_path(value: str, manifest_path: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    repository_path = ROOT / path
    if repository_path.exists():
        return repository_path
    return manifest_path.parent / path


def _validate_file(record: dict[str, Any], manifest_path: Path) -> Path:
    path = _resolve_record_path(record["path"], manifest_path)
    if not path.is_file():
        raise VisualValidationError(f"视觉文件不存在：{path}")
    body = path.read_bytes()
    if hashlib.sha256(body).hexdigest() != record["sha256"]:
        raise VisualValidationError(f"视觉文件SHA-256不一致：{path}")
    if len(body) != record["byte_size"]:
        raise VisualValidationError(f"视觉文件字节数不一致：{path}")
    return path


def validate(queue_path: Path, manifest_path: Path) -> None:
    queue = load_json(queue_path)
    manifest = load_json(manifest_path)
    queue_errors = _schema_errors(ROOT / "schemas/visual-queue.schema.json", queue)
    manifest_errors = _schema_errors(
        ROOT / "schemas/visual-manifest.schema.json", manifest
    )
    if queue_errors or manifest_errors:
        raise VisualValidationError(
            "Schema校验失败：\n- " + "\n- ".join(queue_errors + manifest_errors)
        )
    if manifest["queue_id"] != queue["queue_id"]:
        raise VisualValidationError("Manifest与Queue ID不一致")
    if manifest["preview_only"] != queue["preview_only"]:
        raise VisualValidationError("Manifest与Queue preview_only不一致")

    jobs = {job["job_id"]: job for job in queue["jobs"]}
    assets = {asset["job_id"]: asset for asset in manifest["assets"]}
    if set(jobs) != set(assets):
        raise VisualValidationError("视觉任务与Manifest资产集合不一致")

    for job_id, asset in assets.items():
        if asset["status"] != "passed":
            raise VisualValidationError(
                f"视觉资产未通过：{job_id}：{'; '.join(asset['errors'])}"
            )
        if not asset["logo_embedded"]:
            raise VisualValidationError(f"视觉资产缺少Logo：{job_id}")
        if asset["text_overflow"]:
            raise VisualValidationError(f"视觉资产存在文本溢出：{job_id}")
        if jobs[job_id]["kind"] == "detail_9x16" and not asset["visual_embedded"]:
            raise VisualValidationError(f"详情海报缺少主视觉：{job_id}")
        if asset["placeholder_used"] and not manifest["preview_only"]:
            raise VisualValidationError(f"正式资产使用占位视觉：{job_id}")

        if asset["svg"] is None:
            raise VisualValidationError(f"资产缺少SVG：{job_id}")
        svg_path = _validate_file(asset["svg"], manifest_path)
        svg_text = svg_path.read_text(encoding="utf-8")
        if not re.search(r'<svg[^>]+width="2160"[^>]+height="3840"', svg_text):
            raise VisualValidationError(f"SVG画布尺寸不正确：{svg_path}")
        for required in (jobs[job_id]["content"]["title"], "珩小派"):
            if required and required not in svg_text:
                raise VisualValidationError(
                    f"SVG缺少队列中的准确文本：{job_id}：{required}"
                )

        if asset["png"] is not None:
            png_path = _validate_file(asset["png"], manifest_path)
            validate_png(png_path, width=2160, height=3840)

    summary = manifest["summary"]
    expected = {
        "total": len(assets),
        "passed": sum(a["status"] == "passed" for a in assets.values()),
        "failed": sum(a["status"] == "failed" for a in assets.values()),
        "placeholders": sum(a["placeholder_used"] for a in assets.values()),
        "png_assets": sum(a["png"] is not None for a in assets.values()),
    }
    for key, value in expected.items():
        if summary[key] != value:
            raise VisualValidationError(f"Manifest {key}统计不一致")


def main() -> int:
    args = parse_args()
    try:
        validate(args.queue, args.manifest)
    except (VisualValidationError, RasterizationError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"PASS visual assets: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
