"""Render approved HXP visuals into independent platform-specific templates."""

from __future__ import annotations

import base64
import hashlib
import html
from pathlib import Path
from typing import Any, Mapping

from .approved_assets import ApprovedAssetError, select_latest_approved_assets
from .layout import wrap_text
from .queue import resolve_path
from .rasterizer import RasterizationError, svg_to_png, validate_png
from .svg_renderer import render_detail_svg, render_summary_svg


class MultiFormatExportError(RuntimeError):
    """Raised when a formal multi-platform export cannot be completed."""


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _data_uri(path: Path) -> str:
    if not path.is_file():
        raise MultiFormatExportError(f"视觉资产不存在：{path}")
    mime = {
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(path.suffix.lower())
    if mime is None:
        raise MultiFormatExportError(f"不支持的视觉资产格式：{path}")
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _text(
    lines: tuple[str, ...] | list[str],
    *,
    x: int,
    y: int,
    size: int,
    line_height: int,
    fill: str,
    family: str,
    weight: int = 400,
    anchor: str = "start",
    letter_spacing: int | float = 0,
) -> str:
    if not lines:
        return ""
    spans = []
    for index, line in enumerate(lines):
        spans.append(
            f'<tspan x="{x}" dy="{0 if index == 0 else line_height}">{_escape(line)}</tspan>'
        )
    return (
        f'<text x="{x}" y="{y}" fill="{fill}" font-family="{_escape(family)}" '
        f'font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" '
        f'letter-spacing="{letter_spacing}">{"".join(spans)}</text>'
    )


def _card(x: int, y: int, width: int, height: int, *, radius: int, colors: Mapping[str, Any]) -> str:
    return (
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}" '
        f'fill="{colors["card"]}" fill-opacity="0.94" stroke="{colors["line"]}" '
        f'stroke-width="2" filter="url(#softShadow)"/>'
    )


def _base_svg(
    *,
    width: int,
    height: int,
    colors: Mapping[str, Any],
    body: str,
    defs_extra: str = "",
) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <linearGradient id="backgroundGradient" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{colors['background_top']}"/>
      <stop offset="100%" stop-color="{colors['background_bottom']}"/>
    </linearGradient>
    <radialGradient id="glowA" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="{colors['secondary']}" stop-opacity="0.24"/>
      <stop offset="100%" stop-color="{colors['secondary']}" stop-opacity="0"/>
    </radialGradient>
    <filter id="softShadow" x="-30%" y="-30%" width="160%" height="160%">
      <feDropShadow dx="0" dy="18" stdDeviation="24" flood-color="#0B4F99" flood-opacity="0.12"/>
    </filter>
    {defs_extra}
  </defs>
  <rect width="100%" height="100%" fill="url(#backgroundGradient)"/>
  <circle cx="{int(width * .82)}" cy="{int(height * .22)}" r="{int(min(width, height) * .34)}" fill="url(#glowA)"/>
  <path d="M0 {int(height * .82)} C{int(width * .25)} {int(height * .72)} {int(width * .55)} {int(height * .92)} {width} {int(height * .72)}" fill="none" stroke="{colors['line']}" stroke-opacity="0.42" stroke-width="2"/>
  {body}
</svg>
'''


def _header(
    *,
    content: Mapping[str, Any],
    logo_uri: str,
    width: int,
    margin: int,
    logo_size: int,
    colors: Mapping[str, Any],
    family: str,
    compact: bool = False,
) -> tuple[str, bool]:
    eyebrow = wrap_text(content["eyebrow"], maximum_units=56, maximum_lines=1)
    size = 28 if compact else 34
    pieces = [
        _text(
            eyebrow.lines,
            x=margin,
            y=margin + size,
            size=size,
            line_height=size + 10,
            fill=colors["primary"],
            family=family,
            weight=750,
            letter_spacing=1.5,
        ),
        _text(
            (content["date_label"], content["index_label"]),
            x=margin,
            y=margin + size + 52,
            size=22 if compact else 26,
            line_height=34,
            fill=colors["muted"],
            family=family,
            weight=550,
        ),
        f'<image x="{width - margin - logo_size}" y="{margin}" width="{logo_size}" height="{logo_size}" href="{logo_uri}" preserveAspectRatio="xMidYMid meet"/>',
    ]
    return "".join(pieces), eyebrow.overflow


def _detail_portrait(
    job: Mapping[str, Any],
    *,
    preset: Mapping[str, Any],
    theme: Mapping[str, Any],
    logo_path: Path,
    visual_path: Path,
) -> tuple[str, bool]:
    width, height = int(preset["width"]), int(preset["height"])
    colors, family = theme["colors"], theme["typography"]["fallback_stack"]
    margin, radius = 132, 36
    logo_uri, visual_uri = _data_uri(logo_path), _data_uri(visual_path)
    header, overflow = _header(
        content=job["content"], logo_uri=logo_uri, width=width, margin=margin,
        logo_size=210, colors=colors, family=family,
    )
    content = job["content"]
    title = wrap_text(content["title"], maximum_units=25, maximum_lines=2)
    subtitle = wrap_text(content["subtitle"], maximum_units=45, maximum_lines=2)
    summary = wrap_text(content["summary"], maximum_units=58, maximum_lines=4)
    why = wrap_text("为什么重要｜" + "；".join(content["why_it_matters"][:2]), maximum_units=58, maximum_lines=4)
    follow = wrap_text("后续关注｜" + "；".join(content["follow_up"][:2]), maximum_units=58, maximum_lines=4)
    sources = wrap_text("来源：" + " / ".join(content["source_labels"]), maximum_units=70, maximum_lines=2)
    overflow = overflow or any(v.overflow for v in (title, subtitle, summary, why, follow, sources))
    visual_y, visual_h = 720, 980
    clip = f"clip-{job['job_id'].replace('-', '')}-34"
    defs = f'<clipPath id="{clip}"><rect x="{margin}" y="{visual_y}" width="{width - margin * 2}" height="{visual_h}" rx="{radius}"/></clipPath>'
    pieces = [
        header,
        _text(title.lines, x=margin, y=360, size=104, line_height=122, fill=colors["text"], family=family, weight=820, letter_spacing=-1.5),
        _text(subtitle.lines, x=margin, y=620, size=42, line_height=56, fill=colors["muted"], family=family, weight=500),
        _card(margin, visual_y, width - margin * 2, visual_h, radius=radius, colors=colors),
        f'<image x="{margin}" y="{visual_y}" width="{width - margin * 2}" height="{visual_h}" href="{visual_uri}" preserveAspectRatio="xMidYMid slice" clip-path="url(#{clip})"/>',
        _card(margin, 1770, width - margin * 2, 360, radius=radius, colors=colors),
        _text(("一句话摘要",), x=margin + 44, y=1840, size=36, line_height=48, fill=colors["primary"], family=family, weight=760),
        _text(summary.lines, x=margin + 44, y=1910, size=38, line_height=54, fill=colors["text"], family=family, weight=450),
        _card(margin, 2180, 910, 440, radius=radius, colors=colors),
        _card(1118, 2180, 910, 440, radius=radius, colors=colors),
        _text(why.lines, x=margin + 42, y=2255, size=34, line_height=50, fill=colors["text"], family=family, weight=500),
        _text(follow.lines, x=1160, y=2255, size=34, line_height=50, fill=colors["text"], family=family, weight=500),
        _text(sources.lines, x=margin, y=2740, size=28, line_height=38, fill=colors["muted"], family=family, weight=450),
        _text((theme["brand"]["footer"],), x=width - margin, y=2740, size=28, line_height=38, fill=colors["primary"], family=family, weight=650, anchor="end"),
    ]
    return _base_svg(width=width, height=height, colors=colors, body="".join(pieces), defs_extra=defs), overflow


def _detail_landscape(
    job: Mapping[str, Any],
    *,
    preset: Mapping[str, Any],
    theme: Mapping[str, Any],
    logo_path: Path,
    visual_path: Path,
) -> tuple[str, bool]:
    width, height = int(preset["width"]), int(preset["height"])
    colors, family = theme["colors"], theme["typography"]["fallback_stack"]
    margin, radius = 150, 34
    logo_uri, visual_uri = _data_uri(logo_path), _data_uri(visual_path)
    header, overflow = _header(
        content=job["content"], logo_uri=logo_uri, width=width, margin=margin,
        logo_size=170, colors=colors, family=family, compact=True,
    )
    content = job["content"]
    title = wrap_text(content["title"], maximum_units=22, maximum_lines=2)
    subtitle = wrap_text(content["subtitle"], maximum_units=40, maximum_lines=2)
    summary = wrap_text(content["summary"], maximum_units=48, maximum_lines=4)
    sources = wrap_text("来源：" + " / ".join(content["source_labels"]), maximum_units=62, maximum_lines=2)
    overflow = overflow or any(v.overflow for v in (title, subtitle, summary, sources))
    visual_x, visual_y, visual_w, visual_h = 1370, 190, 1040, 1060
    clip = f"clip-{job['job_id'].replace('-', '')}-169"
    defs = f'<clipPath id="{clip}"><rect x="{visual_x}" y="{visual_y}" width="{visual_w}" height="{visual_h}" rx="{radius}"/></clipPath>'
    pieces = [
        header,
        _text(title.lines, x=margin, y=420, size=104, line_height=118, fill=colors["text"], family=family, weight=820, letter_spacing=-1.5),
        _text(subtitle.lines, x=margin, y=690, size=38, line_height=52, fill=colors["muted"], family=family, weight=500),
        _card(margin, 820, 1080, 330, radius=radius, colors=colors),
        _text(("今日判断",), x=margin + 42, y=890, size=32, line_height=44, fill=colors["primary"], family=family, weight=750),
        _text(summary.lines, x=margin + 42, y=955, size=34, line_height=48, fill=colors["text"], family=family, weight=450),
        _text(sources.lines, x=margin, y=1280, size=24, line_height=34, fill=colors["muted"], family=family, weight=450),
        _card(visual_x, visual_y, visual_w, visual_h, radius=radius, colors=colors),
        f'<image x="{visual_x}" y="{visual_y}" width="{visual_w}" height="{visual_h}" href="{visual_uri}" preserveAspectRatio="xMidYMid slice" clip-path="url(#{clip})"/>',
        _text((theme["brand"]["footer"],), x=width - margin, y=1350, size=24, line_height=32, fill=colors["primary"], family=family, weight=650, anchor="end"),
    ]
    return _base_svg(width=width, height=height, colors=colors, body="".join(pieces), defs_extra=defs), overflow


def _detail_cover(
    job: Mapping[str, Any],
    *,
    preset: Mapping[str, Any],
    theme: Mapping[str, Any],
    logo_path: Path,
    visual_path: Path,
) -> tuple[str, bool]:
    width, height = int(preset["width"]), int(preset["height"])
    colors, family = theme["colors"], theme["typography"]["fallback_stack"]
    margin, radius = 140, 30
    logo_uri, visual_uri = _data_uri(logo_path), _data_uri(visual_path)
    content = job["content"]
    title = wrap_text(content["title"], maximum_units=20, maximum_lines=2)
    subtitle = wrap_text(content["subtitle"], maximum_units=38, maximum_lines=2)
    source = wrap_text("来源：" + " / ".join(content["source_labels"]), maximum_units=50, maximum_lines=1)
    overflow = title.overflow or subtitle.overflow or source.overflow
    visual_x, visual_y, visual_w, visual_h = 1420, 90, 790, 820
    clip = f"clip-{job['job_id'].replace('-', '')}-235"
    defs = f'<clipPath id="{clip}"><rect x="{visual_x}" y="{visual_y}" width="{visual_w}" height="{visual_h}" rx="{radius}"/></clipPath>'
    pieces = [
        _text((content["eyebrow"],), x=margin, y=130, size=28, line_height=36, fill=colors["primary"], family=family, weight=750, letter_spacing=1.5),
        _text(title.lines, x=margin, y=360, size=98, line_height=112, fill=colors["text"], family=family, weight=830, letter_spacing=-1.5),
        _text(subtitle.lines, x=margin, y=645, size=36, line_height=48, fill=colors["muted"], family=family, weight=500),
        _text(source.lines, x=margin, y=875, size=22, line_height=30, fill=colors["muted"], family=family, weight=450),
        f'<image x="{width - margin - 150}" y="{60}" width="150" height="150" href="{logo_uri}" preserveAspectRatio="xMidYMid meet"/>',
        _card(visual_x, visual_y, visual_w, visual_h, radius=radius, colors=colors),
        f'<image x="{visual_x}" y="{visual_y}" width="{visual_w}" height="{visual_h}" href="{visual_uri}" preserveAspectRatio="xMidYMid slice" clip-path="url(#{clip})"/>',
    ]
    return _base_svg(width=width, height=height, colors=colors, body="".join(pieces), defs_extra=defs), overflow


def _summary_custom(
    job: Mapping[str, Any],
    *,
    preset: Mapping[str, Any],
    theme: Mapping[str, Any],
    logo_path: Path,
) -> tuple[str, bool]:
    width, height = int(preset["width"]), int(preset["height"])
    colors, family = theme["colors"], theme["typography"]["fallback_stack"]
    margin = int(preset["safe_area"]["left"])
    logo_uri = _data_uri(logo_path)
    content = job["content"]
    landscape = width > height
    cover = preset["preset_id"] == "wechat_cover_235x1"
    title_units = 20 if cover else (28 if landscape else 26)
    title = wrap_text(content["title"], maximum_units=title_units, maximum_lines=2)
    summary = wrap_text(content["summary"], maximum_units=48 if landscape else 58, maximum_lines=3)
    focuses = content["focus_titles"][: (3 if cover else 4 if landscape else 6)]
    overflow = title.overflow or summary.overflow
    pieces = [
        _text((content["eyebrow"],), x=margin, y=margin + 28, size=28 if landscape else 34, line_height=40, fill=colors["primary"], family=family, weight=750),
        _text(title.lines, x=margin, y=250 if cover else 340, size=92 if landscape else 104, line_height=110 if landscape else 122, fill=colors["text"], family=family, weight=830, letter_spacing=-1.5),
        f'<image x="{width - margin - (150 if cover else 190)}" y="{margin}" width="{150 if cover else 190}" height="{150 if cover else 190}" href="{logo_uri}" preserveAspectRatio="xMidYMid meet"/>',
    ]
    if cover:
        y = 650
        for index, focus in enumerate(focuses, start=1):
            wrapped = wrap_text(f"{index:02d}  {focus}", maximum_units=30, maximum_lines=1)
            overflow = overflow or wrapped.overflow
            pieces.append(_text(wrapped.lines, x=margin + (index - 1) * 650, y=y, size=30, line_height=40, fill=colors["muted"], family=family, weight=600))
        pieces.append(_text(summary.lines, x=margin, y=820, size=28, line_height=38, fill=colors["muted"], family=family, weight=450))
    elif landscape:
        pieces.append(_card(margin, 600, 1050, 500, radius=34, colors=colors))
        pieces.append(_text(("今日判断",), x=margin + 42, y=680, size=34, line_height=46, fill=colors["primary"], family=family, weight=750))
        pieces.append(_text(summary.lines, x=margin + 42, y=755, size=36, line_height=52, fill=colors["text"], family=family, weight=450))
        start_x, start_y = 1340, 360
        for index, focus in enumerate(focuses, start=1):
            wrapped = wrap_text(f"{index:02d}  {focus}", maximum_units=26, maximum_lines=2)
            overflow = overflow or wrapped.overflow
            y = start_y + (index - 1) * 220
            pieces.append(_card(start_x, y, 1070, 180, radius=30, colors=colors))
            pieces.append(_text(wrapped.lines, x=start_x + 38, y=y + 72, size=34, line_height=46, fill=colors["text"], family=family, weight=620))
    else:
        pieces.append(_card(margin, 650, width - margin * 2, 360, radius=36, colors=colors))
        pieces.append(_text(("今日判断",), x=margin + 42, y=730, size=36, line_height=48, fill=colors["primary"], family=family, weight=750))
        pieces.append(_text(summary.lines, x=margin + 42, y=805, size=38, line_height=54, fill=colors["text"], family=family, weight=450))
        columns = 2
        card_w = (width - margin * 2 - 48) // columns
        start_y = 1100
        for index, focus in enumerate(focuses, start=1):
            column, row = (index - 1) % columns, (index - 1) // columns
            x, y = margin + column * (card_w + 48), start_y + row * 230
            wrapped = wrap_text(f"{index:02d}  {focus}", maximum_units=26, maximum_lines=2)
            overflow = overflow or wrapped.overflow
            pieces.append(_card(x, y, card_w, 190, radius=30, colors=colors))
            pieces.append(_text(wrapped.lines, x=x + 34, y=y + 72, size=32, line_height=44, fill=colors["text"], family=family, weight=620))
        pieces.append(_text((theme["brand"]["footer"],), x=width - margin, y=height - 100, size=28, line_height=36, fill=colors["primary"], family=family, weight=650, anchor="end"))
    return _base_svg(width=width, height=height, colors=colors, body="".join(pieces)), overflow


def render_platform_svg(
    job: Mapping[str, Any],
    *,
    preset: Mapping[str, Any],
    theme: Mapping[str, Any],
    logo_path: Path,
    visual_path: Path | None,
) -> tuple[str, bool]:
    preset_id = str(preset["preset_id"])
    is_summary = job.get("item_id") is None
    if preset_id == "vertical_9x16":
        if is_summary:
            svg, metadata = render_summary_svg(job, theme=theme, logo_path=logo_path)
        else:
            if visual_path is None:
                raise MultiFormatExportError(f"详情海报缺少主视觉：{job['job_id']}")
            svg, metadata = render_detail_svg(
                job, theme=theme, logo_path=logo_path, visual_path=visual_path
            )
        return svg, bool(metadata["text_overflow"])
    if is_summary:
        return _summary_custom(job, preset=preset, theme=theme, logo_path=logo_path)
    if visual_path is None:
        raise MultiFormatExportError(f"详情海报缺少主视觉：{job['job_id']}")
    if preset_id == "portrait_3x4":
        return _detail_portrait(job, preset=preset, theme=theme, logo_path=logo_path, visual_path=visual_path)
    if preset_id == "landscape_16x9":
        return _detail_landscape(job, preset=preset, theme=theme, logo_path=logo_path, visual_path=visual_path)
    if preset_id == "wechat_cover_235x1":
        return _detail_cover(job, preset=preset, theme=theme, logo_path=logo_path, visual_path=visual_path)
    raise MultiFormatExportError(f"未知导出预设：{preset_id}")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def _record(path: Path) -> dict[str, Any]:
    body = path.read_bytes()
    root = Path(__file__).resolve().parents[1]
    try:
        label = path.resolve().relative_to(root).as_posix()
    except ValueError:
        label = path.resolve().as_posix()
    return {"path": label, "sha256": hashlib.sha256(body).hexdigest(), "byte_size": len(body)}


def export_platform_assets(
    *,
    visual_queue: Mapping[str, Any],
    request_queue: Mapping[str, Any],
    review_batch: Mapping[str, Any],
    presets_config: Mapping[str, Any],
    theme: Mapping[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    """Render every approved detail and summary job in every configured preset."""
    try:
        approved = select_latest_approved_assets(
            visual_queue=visual_queue,
            request_queue=request_queue,
            review_batch=review_batch,
        )
    except ApprovedAssetError as exc:
        raise MultiFormatExportError(str(exc)) from exc

    logo_path = resolve_path(str(visual_queue["logo_path"]))
    if not logo_path.is_file():
        raise MultiFormatExportError(f"正式Logo文件不存在：{logo_path}")
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    compact = str(visual_queue["date"]).replace("-", "")
    exports: list[dict[str, Any]] = []
    preset_counts: dict[str, int] = {}

    for preset in presets_config.get("presets", []):
        preset_id = str(preset["preset_id"])
        width, height = int(preset["width"]), int(preset["height"])
        preset_counts[preset_id] = 0
        for job in sorted(visual_queue["jobs"], key=lambda value: int(value["order"])):
            item_id = job.get("item_id")
            selected = approved.get(str(item_id)) if item_id is not None else None
            visual_path = selected["path"] if selected is not None else None
            svg, overflow = render_platform_svg(
                job,
                preset=preset,
                theme=theme,
                logo_path=logo_path,
                visual_path=visual_path,
            )
            base = output_dir / preset_id / f"{job['output_base']}-{preset_id}"
            svg_path, png_path = base.with_suffix(".svg"), base.with_suffix(".png")
            _write_text(svg_path, svg)
            try:
                svg_to_png(svg_path, png_path, width=width, height=height)
                validate_png(png_path, width=width, height=height)
            except RasterizationError as exc:
                raise MultiFormatExportError(str(exc)) from exc
            errors = ["固定平台模板存在文本溢出"] if overflow else []
            exports.append(
                {
                    "export_id": f"export-{compact}-{int(job['order']):02d}-{preset_id}",
                    "job_id": job["job_id"],
                    "item_id": item_id,
                    "preset": preset_id,
                    "width": width,
                    "height": height,
                    "ratio": preset["ratio"],
                    "platforms": preset["platforms"],
                    "source_request_id": selected["request_id"] if selected else None,
                    "source_asset_sha256": selected["sha256"] if selected else None,
                    "review_decision": "approved" if selected else "not_applicable",
                    "svg": _record(svg_path),
                    "png": _record(png_path),
                    "text_overflow": overflow,
                    "crop_safe": True,
                    "status": "failed" if errors else "passed",
                    "errors": errors,
                }
            )
            preset_counts[preset_id] += 1

    failed = sum(value["status"] == "failed" for value in exports)
    return {
        "schema_version": "1.0.0",
        "export_manifest_id": f"export-manifest-{compact}",
        "visual_manifest_id": f"visual-manifest-{compact}",
        "review_batch_id": review_batch["review_batch_id"],
        "date": visual_queue["date"],
        "generated_at": visual_queue["generated_at"],
        "template_version": presets_config["version"],
        "exports": exports,
        "summary": {
            "total": len(exports),
            "passed": len(exports) - failed,
            "failed": failed,
            "preset_counts": preset_counts,
        },
    }
