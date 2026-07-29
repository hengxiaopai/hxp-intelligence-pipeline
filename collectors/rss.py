"""RSS 2.0 and Atom feed parsing without third-party dependencies."""

from __future__ import annotations

import email.utils
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from typing import Any

from .base import CollectionError

PARSER_VERSION = "rss-v0.1.0"


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        cleaned = " ".join(data.split())
        if cleaned:
            self.parts.append(cleaned)


def _plain_text(value: str | None, *, limit: int = 1200) -> str | None:
    if not value:
        return None
    parser = _TextExtractor()
    parser.feed(unescape(value))
    text = " ".join(parser.parts)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] or None


def _iso_datetime(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip()
    try:
        parsed = email.utils.parsedate_to_datetime(candidate)
    except (TypeError, ValueError, OverflowError):
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _children_by_name(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element if _local_name(child.tag) == name]


def _first_text(element: ET.Element, *names: str) -> str | None:
    wanted = {name.lower() for name in names}
    for child in element:
        if _local_name(child.tag) in wanted and child.text:
            value = child.text.strip()
            if value:
                return value
    return None


def _atom_link(entry: ET.Element, base_url: str) -> str | None:
    fallback: str | None = None
    for child in entry:
        if _local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href")
        if not href:
            continue
        resolved = urllib.parse.urljoin(base_url, href)
        relation = child.attrib.get("rel", "alternate")
        if relation == "alternate":
            return resolved
        fallback = fallback or resolved
    return fallback


def _rss_link(item: ET.Element, base_url: str) -> str | None:
    value = _first_text(item, "link")
    return urllib.parse.urljoin(base_url, value) if value else None


def _authors(element: ET.Element) -> list[str]:
    values: list[str] = []
    for child in element:
        name = _local_name(child.tag)
        if name in {"author", "creator"}:
            nested_name = _first_text(child, "name")
            value = nested_name or (child.text.strip() if child.text else "")
            if value and value not in values:
                values.append(value[:120])
    return values


def _tags(element: ET.Element) -> list[str]:
    values: list[str] = []
    for child in element:
        if _local_name(child.tag) != "category":
            continue
        value = child.attrib.get("term") or (child.text.strip() if child.text else "")
        if value and value not in values:
            values.append(value[:80])
    return values


def parse_feed(body: bytes, *, base_url: str, max_items: int = 100) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise CollectionError(f"RSS/Atom XML 解析失败：{exc}") from exc

    root_name = _local_name(root.tag)
    if root_name == "rss":
        channels = _children_by_name(root, "channel")
        if not channels:
            raise CollectionError("RSS 缺少 channel")
        entries = _children_by_name(channels[0], "item")
        mode = "rss"
    elif root_name == "feed":
        entries = _children_by_name(root, "entry")
        mode = "atom"
    else:
        raise CollectionError(f"不支持的 Feed 根节点：{root_name}")

    discovered: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for entry in entries[:max_items]:
        title = _first_text(entry, "title")
        if mode == "atom":
            url = _atom_link(entry, base_url)
            external_id = _first_text(entry, "id") or url
            published = _first_text(entry, "published", "updated")
            summary = _first_text(entry, "summary", "content")
        else:
            url = _rss_link(entry, base_url)
            external_id = _first_text(entry, "guid") or url
            published = _first_text(entry, "pubdate", "date", "published")
            summary = _first_text(entry, "description", "summary", "encoded")

        if not title or not url or not external_id:
            continue
        normalized_url = url.strip()
        if normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)
        discovered.append(
            {
                "external_id": external_id.strip()[:240],
                "title": _plain_text(title, limit=300) or title.strip()[:300],
                "url": normalized_url,
                "published_at": _iso_datetime(published),
                "summary": _plain_text(summary),
                "authors": _authors(entry),
                "tags": _tags(entry),
            }
        )
    return discovered
