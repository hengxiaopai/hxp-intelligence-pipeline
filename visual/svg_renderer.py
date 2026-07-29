"""Render HXP detail and summary posters as deterministic SVG documents."""

from __future__ import annotations

import base64
import html
from pathlib import Path
from typing import Any, Mapping

from .layout import WrappedText, wrap_bullets, wrap_text


class SVGRenderError(ValueError):
    """Raised when required assets or template content are missing."""


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _data_uri(path: Path) -> str:
    if not path.is_file():
        raise SVGRenderError(f"视觉资产不存在：{path}")
    suffix = path.suffix.lower()
    mime = {
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(suffix)
    if mime is None:
        raise SVGRenderError(f"不支持的视觉资产格式：{path}")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


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
    tspans = []
    for index, line in enumerate(lines):
        dy = 0 if index == 0 else line_height
        tspans.append(
            f'<tspan x="{x}" dy="{dy}">{_escape(line)}</tspan>'
        )
    return (
        f'<text x="{x}" y="{y}" fill="{fill}" font-family="{_escape(family)}" '
        f'font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" '
        f'letter-spacing="{letter_spacing}">{"".join(tspans)}</text>'
    )


def _card(x: int, y: int, width: int, height: int, theme: Mapping[str, Any]) -> str:
    colors = theme["colors"]
    radius = int(theme["render"]["card_radius"])
    return (
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}" '
        f'fill="{colors["card"]}" fill-opacity="{theme["render"]["card_opacity"]}" '
        f'stroke="{colors["line"]}" stroke-width="{theme["render"]["stroke_width"]}" '
        f'filter="url(#softShadow)"/>'
    )


def _base_svg(theme: Mapping[str, Any], body: str, defs_extra: str = "") -> str:
    canvas = theme["canvas"]
    colors = theme["colors"]
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{canvas['width']}" height="{canvas['height']}" viewBox="0 0 {canvas['width']} {canvas['height']}">
  <defs>
    <linearGradient id="backgroundGradient" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{colors['background_top']}"/>
      <stop offset="100%" stop-color="{colors['background_bottom']}"/>
    </linearGradient>
    <radialGradient id="glowA" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="{colors['secondary']}" stop-opacity="0.28"/>
      <stop offset="100%" stop-color="{colors['secondary']}" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="glowB" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="{colors['accent']}" stop-opacity="0.20"/>
      <stop offset="100%" stop-color="{colors['accent']}" stop-opacity="0"/>
    </radialGradient>
    <filter id="softShadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="24" stdDeviation="32" flood-color="#0B4F99" flood-opacity="{theme['render']['shadow_opacity']}"/>
    </filter>
    {defs_extra}
  </defs>
  <rect width="100%" height="100%" fill="url(#backgroundGradient)"/>
  <circle cx="1840" cy="520" r="560" fill="url(#glowA)"/>
  <circle cx="220" cy="3180" r="640" fill="url(#glowB)"/>
  <path d="M0 820 C420 710 740 880 1120 790 C1510 700 1830 720 2160 570" fill="none" stroke="{colors['line']}" stroke-opacity="0.45" stroke-width="2"/>
  <path d="M0 3320 C430 3180 850 3380 1290 3220 C1600 3110 1900 3130 2160 3010" fill="none" stroke="{colors['line']}" stroke-opacity="0.35" stroke-width="2"/>
  {body}
</svg>
'''


def _header(
    job: Mapping[str, Any],
    theme: Mapping[str, Any],
    logo_uri: str,
) -> tuple[str, bool]:
    colors = theme["colors"]
    typo = theme["typography"]
    layout = theme["layout"]
    family = typo["fallback_stack"]
    content = job["content"]
    eyebrow = wrap_text(
        content["eyebrow"], maximum_units=66, maximum_lines=1
    )
    subtitle = wrap_text(
        content["subtitle"],
        maximum_units=int(theme["limits"]["subtitle_units_per_line"]),
        maximum_lines=int(theme["limits"]["subtitle_max_lines"]),
    )
    pieces = [
        _text(
            eyebrow.lines,
            x=layout["header"]["x"],
            y=layout["header"]["y"] + 52,
            size=typo["eyebrow_size"],
            line_height=58,
            fill=colors["primary"],
            family=family,
            weight=700,
            letter_spacing=2,
        ),
        _text(
            (content["date_label"],),
            x=layout["header"]["x"],
            y=layout["header"]["y"] + 128,
            size=32,
            line_height=40,
            fill=colors["muted"],
            family=family,
            weight=500,
            letter_spacing=1,
        ),
        _text(
            (content["index_label"],),
            x=layout["header"]["x"] + 330,
            y=layout["header"]["y"] + 128,
            size=32,
            line_height=40,
            fill=colors["muted"],
            family=family,
            weight=600,
            letter_spacing=2,
        ),
        (
            f'<image x="{layout["logo"]["x"]}" y="{layout["logo"]["y"]}" '
            f'width="{layout["logo"]["width"]}" height="{layout["logo"]["height"]}" '
            f'href="{logo_uri}" preserveAspectRatio="xMidYMid meet"/>'
        ),
    ]
    if subtitle.lines:
        pieces.append(
            _text(
                subtitle.lines,
                x=layout["title"]["x"],
                y=layout["title"]["y"] + 320,
                size=typo["subtitle_size"],
                line_height=72,
                fill=colors["muted"],
                family=family,
                weight=500,
            )
        )
    return "".join(pieces), eyebrow.overflow or subtitle.overflow


def render_detail_svg(
    job: Mapping[str, Any],
    *,
    theme: Mapping[str, Any],
    logo_path: Path,
    visual_path: Path,
    placeholder_used: bool = False,
) -> tuple[str, dict[str, Any]]:
    if job["kind"] != "detail_9x16":
        raise SVGRenderError("detail renderer received a non-detail job")
    colors = theme["colors"]
    typo = theme["typography"]
    layout = theme["layout"]
    limits = theme["limits"]
    family = typo["fallback_stack"]
    content = job["content"]
    logo_uri = _data_uri(logo_path)
    visual_uri = _data_uri(visual_path)
    clip_id = "visualClip-" + job["job_id"].replace("-", "")
    defs = (
        f'<clipPath id="{clip_id}"><rect x="{layout["visual"]["x"]}" '
        f'y="{layout["visual"]["y"]}" width="{layout["visual"]["width"]}" '
        f'height="{layout["visual"]["height"]}" rx="{theme["render"]["card_radius"]}"/></clipPath>'
    )

    title = wrap_text(
        content["title"],
        maximum_units=int(limits["title_units_per_line"]),
        maximum_lines=int(limits["title_max_lines"]),
    )
    summary = wrap_text(
        content["summary"],
        maximum_units=int(limits["summary_units_per_line"]),
        maximum_lines=int(limits["summary_max_lines"]),
    )
    confidence_full = wrap_text(
        content["confidence_label"],
        maximum_units=92,
        maximum_lines=2,
    )
    source_line = "来源：" + " / ".join(content["source_labels"])
    sources = wrap_text(
        source_line,
        maximum_units=int(limits["source_units_per_line"]),
        maximum_lines=int(limits["source_max_lines"]),
    )
    conversions = wrap_text(
        content["conversion_label"], maximum_units=92, maximum_lines=2
    )
    why_lines, why_overflow = wrap_bullets(
        content["why_it_matters"],
        maximum_units=int(limits["bullet_units_per_line"]),
        maximum_lines_per_bullet=int(limits["bullet_max_lines"]),
    )
    follow_lines, follow_overflow = wrap_bullets(
        content["follow_up"],
        maximum_units=int(limits["bullet_units_per_line"]),
        maximum_lines_per_bullet=int(limits["bullet_max_lines"]),
    )
    header, header_overflow = _header(job, theme, logo_uri)

    info_chip = wrap_text(content["information_label"], maximum_units=48, maximum_lines=1)
    confidence_short = content["confidence_label"].split("｜", 1)[0]
    confidence_chip = wrap_text(confidence_short, maximum_units=28, maximum_lines=1)

    pieces = [
        header,
        _text(
            title.lines,
            x=layout["title"]["x"],
            y=layout["title"]["y"] + 120,
            size=typo["title_size"],
            line_height=typo["line_height_title"],
            fill=colors["text"],
            family=family,
            weight=800,
            letter_spacing=-2,
        ),
        f'<rect x="{layout["chips"]["x"]}" y="{layout["chips"]["y"]}" width="820" height="88" rx="44" fill="{colors["card"]}" stroke="{colors["line"]}"/>',
        _text(
            info_chip.lines,
            x=layout["chips"]["x"] + 42,
            y=layout["chips"]["y"] + 57,
            size=typo["chip_size"],
            line_height=44,
            fill=colors["primary"],
            family=family,
            weight=650,
        ),
        f'<rect x="{layout["chips"]["x"] + 850}" y="{layout["chips"]["y"]}" width="520" height="88" rx="44" fill="{colors["card"]}" stroke="{colors["line"]}"/>',
        _text(
            confidence_chip.lines,
            x=layout["chips"]["x"] + 892,
            y=layout["chips"]["y"] + 57,
            size=typo["chip_size"],
            line_height=44,
            fill=colors["success"],
            family=family,
            weight=650,
        ),
        _card(
            layout["visual"]["x"],
            layout["visual"]["y"],
            layout["visual"]["width"],
            layout["visual"]["height"],
            theme,
        ),
        (
            f'<image x="{layout["visual"]["x"]}" y="{layout["visual"]["y"]}" '
            f'width="{layout["visual"]["width"]}" height="{layout["visual"]["height"]}" '
            f'href="{visual_uri}" preserveAspectRatio="xMidYMid slice" clip-path="url(#{clip_id})"/>'
        ),
        f'<rect x="{layout["visual"]["x"]}" y="{layout["visual"]["y"]}" width="{layout["visual"]["width"]}" height="{layout["visual"]["height"]}" rx="{theme["render"]["card_radius"]}" fill="none" stroke="{colors["line"]}" stroke-width="2"/>',
        _card(
            layout["summary"]["x"],
            layout["summary"]["y"],
            layout["summary"]["width"],
            layout["summary"]["height"],
            theme,
        ),
        _text(
            ("一句话摘要",),
            x=layout["summary"]["x"] + 54,
            y=layout["summary"]["y"] + 70,
            size=typo["section_title_size"],
            line_height=58,
            fill=colors["primary"],
            family=family,
            weight=750,
        ),
        _text(
            summary.lines,
            x=layout["summary"]["x"] + 54,
            y=layout["summary"]["y"] + 142,
            size=typo["summary_size"],
            line_height=66,
            fill=colors["text"],
            family=family,
            weight=450,
        ),
        _text(
            confidence_full.lines,
            x=layout["summary"]["x"] + 54,
            y=layout["summary"]["y"] + 335,
            size=28,
            line_height=40,
            fill=colors["muted"],
            family=family,
            weight=450,
        ),
        _card(
            layout["analysis_left"]["x"],
            layout["analysis_left"]["y"],
            layout["analysis_left"]["width"],
            layout["analysis_left"]["height"],
            theme,
        ),
        _card(
            layout["analysis_right"]["x"],
            layout["analysis_right"]["y"],
            layout["analysis_right"]["width"],
            layout["analysis_right"]["height"],
            theme,
        ),
        _text(
            ("01  为什么重要",),
            x=layout["analysis_left"]["x"] + 50,
            y=layout["analysis_left"]["y"] + 78,
            size=typo["section_title_size"],
            line_height=58,
            fill=colors["primary"],
            family=family,
            weight=750,
        ),
        _text(
            why_lines,
            x=layout["analysis_left"]["x"] + 50,
            y=layout["analysis_left"]["y"] + 164,
            size=typo["body_size"],
            line_height=typo["line_height_body"],
            fill=colors["text"],
            family=family,
            weight=450,
        ),
        _text(
            ("02  后续关注",),
            x=layout["analysis_right"]["x"] + 50,
            y=layout["analysis_right"]["y"] + 78,
            size=typo["section_title_size"],
            line_height=58,
            fill=colors["accent"],
            family=family,
            weight=750,
        ),
        _text(
            follow_lines,
            x=layout["analysis_right"]["x"] + 50,
            y=layout["analysis_right"]["y"] + 164,
            size=typo["body_size"],
            line_height=typo["line_height_body"],
            fill=colors["text"],
            family=family,
            weight=450,
        ),
        _card(
            layout["footer"]["x"],
            layout["footer"]["y"],
            layout["footer"]["width"],
            layout["footer"]["height"],
            theme,
        ),
        _text(
            conversions.lines,
            x=layout["footer"]["x"] + 50,
            y=layout["footer"]["y"] + 80,
            size=typo["footer_size"],
            line_height=48,
            fill=colors["primary"],
            family=family,
            weight=650,
        ),
        _text(
            sources.lines,
            x=layout["footer"]["x"] + 50,
            y=layout["footer"]["y"] + 178,
            size=typo["footer_size"],
            line_height=48,
            fill=colors["muted"],
            family=family,
            weight=450,
        ),
        _text(
            (theme["brand"]["footer"],),
            x=layout["footer"]["x"] + layout["footer"]["width"] - 50,
            y=layout["footer"]["y"] + 250,
            size=30,
            line_height=40,
            fill=colors["muted"],
            family=family,
            weight=600,
            anchor="end",
            letter_spacing=2,
        ),
    ]
    overflow = any(
        [
            title.overflow,
            summary.overflow,
            confidence_full.overflow,
            sources.overflow,
            conversions.overflow,
            info_chip.overflow,
            confidence_chip.overflow,
            why_overflow,
            follow_overflow,
            header_overflow,
        ]
    )
    metadata = {
        "logo_embedded": True,
        "visual_embedded": True,
        "placeholder_used": bool(placeholder_used),
        "text_overflow": overflow,
        "errors": ["文本超过固定模板上限"] if overflow else [],
    }
    return _base_svg(theme, "".join(pieces), defs), metadata


def render_summary_svg(
    job: Mapping[str, Any],
    *,
    theme: Mapping[str, Any],
    logo_path: Path,
) -> tuple[str, dict[str, Any]]:
    if job["kind"] != "summary_9x16":
        raise SVGRenderError("summary renderer received a non-summary job")
    colors = theme["colors"]
    typo = theme["typography"]
    family = typo["fallback_stack"]
    content = job["content"]
    logo_uri = _data_uri(logo_path)
    header, header_overflow = _header(job, theme, logo_uri)
    title = wrap_text(content["title"], maximum_units=30, maximum_lines=2)
    summary = wrap_text(content["summary"], maximum_units=76, maximum_lines=4)

    pieces = [
        header,
        _text(
            title.lines,
            x=144,
            y=550,
            size=132,
            line_height=158,
            fill=colors["text"],
            family=family,
            weight=800,
            letter_spacing=-2,
        ),
        _card(144, 850, 1872, 320, theme),
        _text(
            ("今日判断",),
            x=198,
            y=925,
            size=42,
            line_height=56,
            fill=colors["primary"],
            family=family,
            weight=750,
        ),
        _text(
            summary.lines,
            x=198,
            y=1005,
            size=44,
            line_height=62,
            fill=colors["text"],
            family=family,
            weight=450,
        ),
    ]
    overflow = header_overflow or title.overflow or summary.overflow

    focus_titles = list(content["focus_titles"])
    card_width = 900
    card_height = 210
    gap_x = 72
    gap_y = 34
    start_y = 1240
    for index, focus in enumerate(focus_titles[:8], start=1):
        column = (index - 1) % 2
        row = (index - 1) // 2
        x = 144 + column * (card_width + gap_x)
        y = start_y + row * (card_height + gap_y)
        wrapped = wrap_text(focus, maximum_units=32, maximum_lines=2)
        overflow = overflow or wrapped.overflow
        pieces.extend(
            [
                _card(x, y, card_width, card_height, theme),
                _text(
                    (f"{index:02d}",),
                    x=x + 42,
                    y=y + 70,
                    size=34,
                    line_height=44,
                    fill=colors["primary"],
                    family=family,
                    weight=800,
                    letter_spacing=2,
                ),
                _text(
                    wrapped.lines,
                    x=x + 126,
                    y=y + 72,
                    size=44,
                    line_height=60,
                    fill=colors["text"],
                    family=family,
                    weight=650,
                ),
            ]
        )

    thread_y = start_y + 4 * (card_height + gap_y) + 40
    pieces.append(_card(144, thread_y, 1872, 500, theme))
    pieces.append(
        _text(
            ("今日主线",),
            x=198,
            y=thread_y + 80,
            size=42,
            line_height=56,
            fill=colors["primary"],
            family=family,
            weight=750,
        )
    )
    thread_lines: list[str] = []
    for thread_index, thread in enumerate(content["main_threads"], start=1):
        wrapped = wrap_text(thread, maximum_units=76, maximum_lines=2)
        overflow = overflow or wrapped.overflow
        for line_index, line in enumerate(wrapped.lines):
            prefix = f"{thread_index}. " if line_index == 0 else "   "
            thread_lines.append(prefix + line)
    pieces.append(
        _text(
            thread_lines,
            x=198,
            y=thread_y + 160,
            size=40,
            line_height=58,
            fill=colors["text"],
            family=family,
            weight=450,
        )
    )

    lower_y = thread_y + 570
    pieces.extend(
        [
            _card(144, lower_y, 900, 560, theme),
            _card(1116, lower_y, 900, 560, theme),
            _text(
                ("内容机会",),
                x=198,
                y=lower_y + 80,
                size=42,
                line_height=56,
                fill=colors["primary"],
                family=family,
                weight=750,
            ),
            _text(
                ("产品与风险",),
                x=1170,
                y=lower_y + 80,
                size=42,
                line_height=56,
                fill=colors["accent"],
                family=family,
                weight=750,
            ),
        ]
    )
    opportunity_lines: list[str] = []
    for index, value in enumerate(content["content_opportunities"], start=1):
        wrapped = wrap_text(value, maximum_units=34, maximum_lines=2)
        overflow = overflow or wrapped.overflow
        for line_index, line in enumerate(wrapped.lines):
            opportunity_lines.append((f"{index}. " if line_index == 0 else "   ") + line)
    pieces.append(
        _text(
            opportunity_lines,
            x=198,
            y=lower_y + 160,
            size=39,
            line_height=58,
            fill=colors["text"],
            family=family,
            weight=450,
        )
    )

    right_lines: list[str] = []
    if content.get("product_opportunity"):
        wrapped = wrap_text(
            "产品：" + content["product_opportunity"],
            maximum_units=34,
            maximum_lines=3,
        )
        overflow = overflow or wrapped.overflow
        right_lines.extend(wrapped.lines)
    if content.get("risk_reminder"):
        wrapped = wrap_text(
            "风险：" + content["risk_reminder"],
            maximum_units=34,
            maximum_lines=3,
        )
        overflow = overflow or wrapped.overflow
        if right_lines:
            right_lines.append("")
        right_lines.extend(wrapped.lines)
    pieces.append(
        _text(
            right_lines,
            x=1170,
            y=lower_y + 160,
            size=39,
            line_height=60,
            fill=colors["text"],
            family=family,
            weight=450,
        )
    )
    pieces.extend(
        [
            f'<rect x="144" y="3650" width="1872" height="2" fill="{colors["line"]}"/>',
            _text(
                (content["conversion_label"],),
                x=144,
                y=3720,
                size=34,
                line_height=46,
                fill=colors["muted"],
                family=family,
                weight=650,
                letter_spacing=1,
            ),
            _text(
                (content["date_label"],),
                x=2016,
                y=3720,
                size=32,
                line_height=42,
                fill=colors["muted"],
                family=family,
                weight=500,
                anchor="end",
            ),
        ]
    )
    metadata = {
        "logo_embedded": True,
        "visual_embedded": False,
        "placeholder_used": False,
        "text_overflow": overflow,
        "errors": ["文本超过固定模板上限"] if overflow else [],
    }
    return _base_svg(theme, "".join(pieces)), metadata
