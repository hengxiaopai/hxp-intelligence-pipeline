"""Rasterize deterministic SVG posters and validate exported PNG assets."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Iterable


class RasterizationError(RuntimeError):
    """Raised when SVG to PNG export cannot produce a trustworthy asset."""


CJK_FAMILY_MARKERS = (
    "noto sans cjk",
    "source han sans",
    "microsoft yahei",
    "pingfang",
    "wenquanyi",
)


def assert_cjk_font_available(families: Iterable[str]) -> str:
    """Return a resolved CJK family or raise an explicit environment error."""
    candidates = [str(value).strip() for value in families if str(value).strip()]
    if not candidates:
        raise RasterizationError("视觉主题未配置任何中文字体候选")

    fc_match = shutil.which("fc-match")
    if fc_match:
        for candidate in candidates:
            result = subprocess.run(
                [fc_match, "-f", "%{family}", candidate],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            resolved = result.stdout.strip()
            lowered = resolved.casefold()
            if result.returncode == 0 and any(
                marker in lowered for marker in CJK_FAMILY_MARKERS
            ):
                return resolved
        raise RasterizationError(
            "未找到可用的CJK字体。请安装 Noto Sans CJK SC、Source Han Sans SC、"
            "Microsoft YaHei 或 PingFang SC；仓库不会分发字体文件。"
        )

    known_files = [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/msyhbd.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/Library/Fonts/NotoSansCJKsc-Regular.otf"),
    ]
    for path in known_files:
        if path.is_file():
            return path.stem

    raise RasterizationError(
        "无法检测系统CJK字体，且未找到 fontconfig。请先安装中文字体与 fc-match，"
        "再执行正式PNG导出。"
    )


def svg_to_png(
    svg_path: Path,
    png_path: Path,
    *,
    width: int,
    height: int,
) -> None:
    """Rasterize one SVG at the exact requested output dimensions."""
    if not svg_path.is_file():
        raise RasterizationError(f"SVG文件不存在：{svg_path}")
    try:
        import cairosvg
    except ImportError as exc:
        raise RasterizationError(
            "缺少 CairoSVG。请安装 requirements-dev.txt 后重试。"
        ) from exc

    png_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = png_path.with_suffix(png_path.suffix + ".tmp")
    try:
        cairosvg.svg2png(
            url=str(svg_path),
            write_to=str(temporary),
            output_width=width,
            output_height=height,
        )
        temporary.replace(png_path)
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        raise RasterizationError(f"SVG转PNG失败：{svg_path}：{exc}") from exc


def validate_png(path: Path, *, width: int, height: int) -> None:
    """Check PNG signature, exact dimensions and a usable color mode."""
    if not path.is_file():
        raise RasterizationError(f"PNG文件不存在：{path}")
    try:
        from PIL import Image
    except ImportError as exc:
        raise RasterizationError(
            "缺少 Pillow，无法验证PNG尺寸。请安装 requirements-dev.txt。"
        ) from exc

    try:
        with Image.open(path) as image:
            image.load()
            if image.format != "PNG":
                raise RasterizationError(f"输出文件不是PNG：{path}")
            if image.size != (width, height):
                raise RasterizationError(
                    f"PNG尺寸错误：{path}，实际{image.width}×{image.height}，"
                    f"应为{width}×{height}"
                )
            if image.mode not in {"RGB", "RGBA"}:
                raise RasterizationError(
                    f"PNG颜色模式不受支持：{path}：{image.mode}"
                )
    except RasterizationError:
        raise
    except Exception as exc:
        raise RasterizationError(f"PNG无法读取：{path}：{exc}") from exc
