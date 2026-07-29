"""Conservative parser for official HTML article index pages.

The parser intentionally extracts only semantic ``<article>`` blocks. It does
not attempt broad link scraping, which reduces navigation, advertising, and
footer noise. A source requiring custom selectors should receive a dedicated
adapter in a later phase.
"""

from __future__ import annotations

import hashlib
import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

PARSER_VERSION = "html-index-v0.1.0"


def _clean(value: str, *, limit: int) -> str:
    return re.sub(r"\s+", " ", value).strip()[:limit]


def _iso_datetime(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip()
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(candidate, "%Y-%m-%d")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class _Article:
    href: str | None = None
    title_parts: list[str] = field(default_factory=list)
    summary_parts: list[str] = field(default_factory=list)
    time_value: str | None = None
    authors: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


class _ArticleParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.article_depth = 0
        self.current: _Article | None = None
        self.in_heading = 0
        self.in_summary = 0
        self.in_author = 0
        self.in_tag = 0
        self.articles: list[_Article] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): value or "" for key, value in attrs}
        tag = tag.lower()
        if tag == "article":
            if self.article_depth == 0:
                self.current = _Article()
            self.article_depth += 1
            return
        if not self.current:
            return

        classes = set(attributes.get("class", "").lower().split())
        if tag == "a" and not self.current.href:
            href = attributes.get("href")
            if href:
                self.current.href = urllib.parse.urljoin(self.base_url, href)
        if tag in {"h1", "h2", "h3", "h4"}:
            self.in_heading += 1
        if tag == "p" or classes.intersection({"summary", "excerpt", "description"}):
            self.in_summary += 1
        if tag == "time":
            self.current.time_value = attributes.get("datetime") or self.current.time_value
        if classes.intersection({"author", "byline"}) or attributes.get("rel") == "author":
            self.in_author += 1
        if classes.intersection({"tag", "category", "topic"}):
            self.in_tag += 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.current:
            if tag in {"h1", "h2", "h3", "h4"} and self.in_heading:
                self.in_heading -= 1
            if tag == "p" and self.in_summary:
                self.in_summary -= 1
            if tag in {"span", "a", "div"} and self.in_author:
                self.in_author -= 1
            if tag in {"span", "a", "div"} and self.in_tag:
                self.in_tag -= 1
        if tag == "article" and self.article_depth:
            self.article_depth -= 1
            if self.article_depth == 0 and self.current:
                self.articles.append(self.current)
                self.current = None
                self.in_heading = self.in_summary = self.in_author = self.in_tag = 0

    def handle_data(self, data: str) -> None:
        if not self.current:
            return
        value = _clean(data, limit=500)
        if not value:
            return
        if self.in_heading:
            self.current.title_parts.append(value)
        elif self.in_author:
            if value not in self.current.authors:
                self.current.authors.append(value[:120])
        elif self.in_tag:
            if value not in self.current.tags:
                self.current.tags.append(value[:80])
        elif self.in_summary and len(" ".join(self.current.summary_parts)) < 1200:
            self.current.summary_parts.append(value)
        elif self.current.time_value is None:
            # Text-only <time> elements are accepted when no datetime attribute exists.
            candidate = _iso_datetime(value)
            if candidate:
                self.current.time_value = candidate


def parse_html_index(
    body: bytes,
    *,
    base_url: str,
    encoding: str = "utf-8",
    max_items: int = 100,
) -> tuple[list[dict[str, Any]], list[str]]:
    text = body.decode(encoding, errors="replace")
    parser = _ArticleParser(base_url)
    parser.feed(text)

    warnings: list[str] = []
    if not parser.articles:
        warnings.append("页面未发现语义化 <article> 区块；需要专用解析器")

    discovered: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for article in parser.articles:
        title = _clean(" ".join(article.title_parts), limit=300)
        summary = _clean(" ".join(article.summary_parts), limit=1200)
        if not article.href or not title:
            continue
        if article.href in seen_urls:
            continue
        seen_urls.add(article.href)
        external_id = "html:" + hashlib.sha256(article.href.encode("utf-8")).hexdigest()[:32]
        discovered.append(
            {
                "external_id": external_id,
                "title": title,
                "url": article.href,
                "published_at": _iso_datetime(article.time_value),
                "summary": summary or None,
                "authors": article.authors,
                "tags": article.tags,
            }
        )
        if len(discovered) >= max_items:
            break
    return discovered, warnings
