"""Build and persist raw collection snapshots."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base import (
    FetchResult,
    SourceConfig,
    assert_supported_source,
    fetch_live_source,
)
from .html_index import PARSER_VERSION as HTML_PARSER_VERSION
from .html_index import parse_html_index
from .rss import PARSER_VERSION as RSS_PARSER_VERSION
from .rss import parse_feed


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _snapshot_id(source: SourceConfig, retrieved_at: datetime) -> str:
    timestamp = retrieved_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = source.registry_id.removeprefix("registry-")
    return f"snapshot-{timestamp}-{slug}"


def _fixture_fetch_result(source: SourceConfig, body: bytes) -> FetchResult:
    if source.collection_method == "rss":
        content_type = "application/rss+xml"
    else:
        content_type = "text/html"
    return FetchResult(
        requested_url=source.url,
        final_url=source.url,
        status=200,
        headers={"content-type": f"{content_type}; charset=utf-8"},
        content_type=content_type,
        body=body,
    )


def _parse(
    source: SourceConfig,
    body: bytes,
    *,
    max_items: int,
) -> tuple[list[dict[str, Any]], list[str], str]:
    if source.collection_method == "rss":
        return parse_feed(body, base_url=source.url, max_items=max_items), [], RSS_PARSER_VERSION
    if source.collection_method == "html_index":
        items, warnings = parse_html_index(
            body,
            base_url=source.url,
            max_items=max_items,
        )
        return items, warnings, HTML_PARSER_VERSION
    raise ValueError(f"unsupported collection method: {source.collection_method}")


def _build_snapshot(
    source: SourceConfig,
    fetch: FetchResult,
    *,
    fetch_mode: str,
    retrieved_at: datetime,
    max_items: int,
) -> dict[str, Any]:
    items, warnings, parser_version = _parse(source, fetch.body, max_items=max_items)
    if not items:
        warnings.append("本次快照未发现可解析条目")
    return {
        "schema_version": "1.0.0",
        "snapshot_id": _snapshot_id(source, retrieved_at),
        "source_registry_id": source.registry_id,
        "requested_url": fetch.requested_url,
        "final_url": fetch.final_url,
        "collection_method": source.collection_method,
        "fetch_mode": fetch_mode,
        "retrieved_at": _format_datetime(retrieved_at),
        "http_status": fetch.status,
        "content_type": fetch.content_type,
        "content_hash": "sha256:" + hashlib.sha256(fetch.body).hexdigest(),
        "byte_size": len(fetch.body),
        "body_path": "pending",
        "parser_version": parser_version,
        "selected_headers": fetch.headers,
        "items": items,
        "warnings": list(dict.fromkeys(warnings)),
    }


def collect_from_bytes(
    source: SourceConfig,
    body: bytes,
    *,
    max_items: int = 100,
    retrieved_at: datetime | None = None,
) -> tuple[dict[str, Any], bytes]:
    """Parse fixture bytes without performing a network request."""
    assert_supported_source(source, live=False)
    observed_at = retrieved_at or _utc_now()
    fetch = _fixture_fetch_result(source, body)
    return (
        _build_snapshot(
            source,
            fetch,
            fetch_mode="fixture",
            retrieved_at=observed_at,
            max_items=max_items,
        ),
        body,
    )


def collect_live(
    source: SourceConfig,
    *,
    max_items: int = 100,
    timeout: int = 15,
) -> tuple[dict[str, Any], bytes]:
    """Fetch one registered source after all live safety checks pass."""
    fetch = fetch_live_source(source, timeout=timeout)
    observed_at = _utc_now()
    return (
        _build_snapshot(
            source,
            fetch,
            fetch_mode="live",
            retrieved_at=observed_at,
            max_items=max_items,
        ),
        fetch.body,
    )


def write_snapshot(
    snapshot: dict[str, Any],
    body: bytes,
    *,
    output_dir: Path,
) -> tuple[Path, Path, dict[str, Any]]:
    """Write raw body first, then atomically replace snapshot metadata."""
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_id = str(snapshot["snapshot_id"])
    extension = ".xml" if snapshot["collection_method"] == "rss" else ".html"
    body_path = output_dir / f"{snapshot_id}{extension}"
    metadata_path = output_dir / f"{snapshot_id}.json"

    body_path.write_bytes(body)
    materialized = deepcopy(snapshot)
    materialized["body_path"] = body_path.as_posix()

    temporary = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(materialized, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(metadata_path)
    return metadata_path, body_path, materialized
