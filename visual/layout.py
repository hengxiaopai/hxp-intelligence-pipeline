"""Deterministic text wrapping and overflow checks for fixed SVG posters."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class WrappedText:
    lines: tuple[str, ...]
    overflow: bool
    original: str


def char_units(character: str) -> int:
    if character == "\t":
        return 4
    if character in "\r\n":
        return 0
    width = unicodedata.east_asian_width(character)
    return 2 if width in {"W", "F", "A"} else 1


def display_units(text: str) -> int:
    return sum(char_units(character) for character in str(text))


def _trim_trailing_space(value: str) -> str:
    return value.rstrip(" \t")


def _ellipsize(value: str, maximum_units: int) -> str:
    ellipsis = "…"
    budget = max(0, maximum_units - display_units(ellipsis))
    output: list[str] = []
    used = 0
    for character in value:
        width = char_units(character)
        if used + width > budget:
            break
        output.append(character)
        used += width
    return _trim_trailing_space("".join(output)) + ellipsis


def wrap_text(
    text: str,
    *,
    maximum_units: int,
    maximum_lines: int,
    ellipsis_on_overflow: bool = True,
) -> WrappedText:
    """Wrap by display width without relying on a particular installed font."""
    normalized = " ".join(str(text).replace("\r", " ").splitlines()).strip()
    if not normalized:
        return WrappedText(lines=tuple(), overflow=False, original=str(text))
    if maximum_units < 1 or maximum_lines < 1:
        raise ValueError("maximum_units and maximum_lines must be positive")

    lines: list[str] = []
    current: list[str] = []
    used = 0
    index = 0
    overflow = False

    while index < len(normalized):
        character = normalized[index]
        width = char_units(character)
        if current and used + width > maximum_units:
            lines.append(_trim_trailing_space("".join(current)))
            current = []
            used = 0
            if len(lines) >= maximum_lines:
                overflow = True
                break
            continue
        if not current and width > maximum_units:
            lines.append(character)
            index += 1
            if len(lines) >= maximum_lines and index < len(normalized):
                overflow = True
                break
            continue
        current.append(character)
        used += width
        index += 1

    if not overflow and current:
        lines.append(_trim_trailing_space("".join(current)))
    if len(lines) > maximum_lines:
        lines = lines[:maximum_lines]
        overflow = True
    if index < len(normalized):
        overflow = True

    if overflow and lines and ellipsis_on_overflow:
        lines[-1] = _ellipsize(lines[-1], maximum_units)
    return WrappedText(lines=tuple(lines), overflow=overflow, original=str(text))


def wrap_bullets(
    values: Iterable[str],
    *,
    maximum_units: int,
    maximum_lines_per_bullet: int,
    maximum_bullets: int = 3,
) -> tuple[tuple[str, ...], bool]:
    lines: list[str] = []
    overflow = False
    items = list(values)
    if len(items) > maximum_bullets:
        items = items[:maximum_bullets]
        overflow = True
    for value in items:
        wrapped = wrap_text(
            value,
            maximum_units=max(4, maximum_units - 3),
            maximum_lines=maximum_lines_per_bullet,
        )
        if wrapped.overflow:
            overflow = True
        for line_index, line in enumerate(wrapped.lines):
            prefix = "• " if line_index == 0 else "  "
            lines.append(prefix + line)
    return tuple(lines), overflow
