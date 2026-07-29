"""Final brand-layer polish for independent platform exports."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Any, Mapping

from .multiformat import export_platform_assets as _base_export_platform_assets
from .queue import resolve_path
from .rasterizer import svg_to_png, validate_png


class ExportPolishError(RuntimeError):
    """Raised when the final brand layer cannot be applied safely."""


def _logo_uri(path: Path) -> str:
    mime = {
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(path.suffix.lower())
    if mime is None or not path.is_file():
        raise ExportPolishError(f"无法嵌入正式Logo：{path}")
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _resolve_output(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[1] / path


def _record(path: Path) -> dict[str, Any]:
    body = path.read_bytes()
    root = Path(__file__).resolve().parents[1]
    try:
        label = path.resolve().relative_to(root).as_posix()
    except ValueError:
        label = path.resolve().as_posix()
    return {"path": label, "sha256": hashlib.sha256(body).hexdigest(), "byte_size": len(body)}


def _overlay_for(preset: str, *, width: int, logo_uri: str) -> str:
    if preset == "landscape_16x9":
        size, x, y = 132, width - 160 - 132, 42
    elif preset == "wechat_cover_235x1":
        size, x, y = 118, width - 135 - 118, 34
    else:
        return ""
    return (
        f'<rect x="{x - 14}" y="{y - 14}" width="{size + 28}" height="{size + 28}" '
        f'rx="28" fill="#FFFFFF" fill-opacity="0.88" stroke="#B9D7F5" stroke-width="2"/>'
        f'<image x="{x}" y="{y}" width="{size}" height="{size}" href="{logo_uri}" '
        f'preserveAspectRatio="xMidYMid meet"/>'
    )


def export_platform_assets(
    *,
    visual_queue: Mapping[str, Any],
    request_queue: Mapping[str, Any],
    review_batch: Mapping[str, Any],
    presets_config: Mapping[str, Any],
    theme: Mapping[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    """Render exports, then place the brand layer above wide-format main visuals."""
    manifest = _base_export_platform_assets(
        visual_queue=visual_queue,
        request_queue=request_queue,
        review_batch=review_batch,
        presets_config=presets_config,
        theme=theme,
        output_dir=output_dir,
    )
    logo_path = resolve_path(str(visual_queue["logo_path"]))
    logo_uri = _logo_uri(logo_path)

    for export in manifest["exports"]:
        overlay = _overlay_for(
            str(export["preset"]),
            width=int(export["width"]),
            logo_uri=logo_uri,
        )
        if not overlay:
            continue
        svg_path = _resolve_output(export["svg"]["path"])
        png_path = _resolve_output(export["png"]["path"])
        svg = svg_path.read_text(encoding="utf-8")
        if "</svg>" not in svg:
            raise ExportPolishError(f"SVG文档不完整：{svg_path}")
        svg_path.write_text(svg.replace("</svg>", overlay + "\n</svg>"), encoding="utf-8")
        svg_to_png(
            svg_path,
            png_path,
            width=int(export["width"]),
            height=int(export["height"]),
        )
        validate_png(
            png_path,
            width=int(export["width"]),
            height=int(export["height"]),
        )
        export["svg"] = _record(svg_path)
        export["png"] = _record(png_path)

    return manifest
