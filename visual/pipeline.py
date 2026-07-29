"""Render a visual queue into SVG/PNG assets and a deterministic manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .queue import load_json, resolve_path
from .rasterizer import (
    RasterizationError,
    assert_cjk_font_available,
    svg_to_png,
    validate_png,
)
from .svg_renderer import SVGRenderError, render_detail_svg, render_summary_svg


class VisualPipelineError(RuntimeError):
    """Raised when poster rendering or manifest generation fails."""


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    _write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _relative(path: Path) -> str:
    root = Path(__file__).resolve().parents[1]
    resolved = path.resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved.as_posix()


def _file_record(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    body = path.read_bytes()
    return {
        "path": _relative(path),
        "sha256": hashlib.sha256(body).hexdigest(),
        "byte_size": len(body),
    }


def _font_candidates(theme: Mapping[str, Any]) -> list[str]:
    typography = theme.get("typography", {})
    result = [str(typography.get("primary_family", "")).strip()]
    fallback = str(typography.get("fallback_stack", ""))
    result.extend(part.strip() for part in fallback.split(","))
    return [value for value in dict.fromkeys(result) if value]


def render_visual_queue(
    *,
    queue: Mapping[str, Any],
    theme: Mapping[str, Any],
    output_dir: Path,
    placeholder_path: Path | None = None,
    rasterize: bool = True,
) -> dict[str, Any]:
    """Render all queue jobs and return a visual manifest."""
    canvas = queue["canvas"]
    width = int(canvas["width"])
    height = int(canvas["height"])
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    logo_path = resolve_path(str(queue["logo_path"]))
    if not logo_path.is_file():
        raise VisualPipelineError(f"Logo文件不存在：{logo_path}")

    if rasterize:
        assert_cjk_font_available(_font_candidates(theme))

    assets: list[dict[str, Any]] = []
    for job in sorted(queue["jobs"], key=lambda value: int(value["order"])):
        errors: list[str] = []
        metadata = {
            "logo_embedded": False,
            "visual_embedded": False,
            "placeholder_used": False,
            "text_overflow": False,
            "errors": [],
        }
        svg_path = output_dir / f"{job['output_base']}.svg"
        png_path = output_dir / f"{job['output_base']}.png"

        try:
            if job["kind"] == "detail_9x16":
                visual_value = job.get("visual_asset_path")
                placeholder_used = False
                if visual_value:
                    visual_path = resolve_path(str(visual_value))
                else:
                    if not queue["asset_policy"]["allow_placeholder"]:
                        raise VisualPipelineError(
                            f"详情海报缺少主视觉：{job['job_id']}"
                        )
                    if placeholder_path is None or not placeholder_path.is_file():
                        raise VisualPipelineError(
                            f"预览任务缺少占位视觉：{job['job_id']}"
                        )
                    visual_path = placeholder_path.resolve()
                    placeholder_used = True
                svg, metadata = render_detail_svg(
                    job,
                    theme=theme,
                    logo_path=logo_path,
                    visual_path=visual_path,
                    placeholder_used=placeholder_used,
                )
            elif job["kind"] == "summary_9x16":
                svg, metadata = render_summary_svg(
                    job,
                    theme=theme,
                    logo_path=logo_path,
                )
            else:
                raise VisualPipelineError(f"未知视觉任务类型：{job['kind']}")

            _write_text(svg_path, svg)
            errors.extend(str(value) for value in metadata.get("errors", []))

            if metadata.get("placeholder_used") and not queue.get("preview_only"):
                errors.append("正式视觉队列禁止使用占位主视觉")
            if metadata.get("text_overflow"):
                errors.append("固定模板存在文本溢出")

            if rasterize and not errors:
                svg_to_png(svg_path, png_path, width=width, height=height)
                validate_png(png_path, width=width, height=height)
        except (SVGRenderError, RasterizationError, VisualPipelineError) as exc:
            errors.append(str(exc))
        except Exception as exc:
            errors.append(f"未预期视觉渲染错误：{exc}")

        status = "failed" if errors else "passed"
        assets.append(
            {
                "job_id": job["job_id"],
                "kind": job["kind"],
                "width": width,
                "height": height,
                "svg": _file_record(svg_path),
                "png": _file_record(png_path) if rasterize else None,
                "logo_embedded": bool(metadata.get("logo_embedded")),
                "visual_embedded": bool(metadata.get("visual_embedded")),
                "placeholder_used": bool(metadata.get("placeholder_used")),
                "text_overflow": bool(metadata.get("text_overflow")),
                "status": status,
                "errors": list(dict.fromkeys(errors)),
            }
        )

    failed = sum(asset["status"] == "failed" for asset in assets)
    return {
        "schema_version": "1.0.0",
        "manifest_id": "visual-manifest-" + str(queue["date"]).replace("-", ""),
        "queue_id": queue["queue_id"],
        "generated_at": queue["generated_at"],
        "preview_only": bool(queue["preview_only"]),
        "assets": assets,
        "summary": {
            "total": len(assets),
            "passed": len(assets) - failed,
            "failed": failed,
            "placeholders": sum(asset["placeholder_used"] for asset in assets),
            "png_assets": sum(asset["png"] is not None for asset in assets),
        },
    }
