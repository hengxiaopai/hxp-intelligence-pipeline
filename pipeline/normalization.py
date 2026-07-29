"""Deterministic normalization and fingerprint helpers.

These functions are intentionally rule-based. They remove formatting variance
without pretending to infer entities, actions, or causal meaning. Those fields
must be supplied explicitly by the Collector or editor.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, Mapping

SPACE_RE = re.compile(r"\s+")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
LATIN_TOKEN_RE = re.compile(r"[a-z0-9]+")


def normalize_text(value: str) -> str:
    """Normalize width, case, punctuation, and whitespace deterministically."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    characters: list[str] = []
    for character in normalized:
        if character.isalnum():
            characters.append(character)
        else:
            characters.append(" ")
    return SPACE_RE.sub(" ", "".join(characters)).strip()


def load_alias_map(path: Path) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"实体别名文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"实体别名 JSON 无效：{path}:{exc.lineno}:{exc.colno}"
        ) from exc

    reverse: dict[str, str] = {}
    for entry in payload.get("entities", []):
        canonical = str(entry["canonical"]).strip()
        values = [canonical, *entry.get("aliases", [])]
        for value in values:
            key = normalize_text(str(value))
            if not key:
                continue
            existing = reverse.get(key)
            if existing and existing != canonical:
                raise ValueError(f"实体别名冲突：{value} -> {existing} / {canonical}")
            reverse[key] = canonical
    return reverse


def canonicalize_entities(
    entities: Iterable[str],
    alias_map: Mapping[str, str] | None = None,
) -> list[str]:
    """Map aliases and return a stable, de-duplicated entity order."""
    alias_map = alias_map or {}
    canonical: dict[str, str] = {}
    for raw_entity in entities:
        value = str(raw_entity).strip()
        key = normalize_text(value)
        if not key:
            continue
        resolved = alias_map.get(key, value)
        resolved_key = normalize_text(resolved)
        canonical[resolved_key] = resolved
    return [canonical[key] for key in sorted(canonical)]


def _fingerprint(prefix: str, payload: Mapping[str, object]) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"{prefix}-" + hashlib.sha256(serialized).hexdigest()[:32]


def event_fingerprint(
    entities: Iterable[str],
    action: str,
    event_object: str,
    event_date: str,
) -> str:
    return _fingerprint(
        "evt",
        {
            "entities": sorted(normalize_text(entity) for entity in entities),
            "action": normalize_text(action),
            "object": normalize_text(event_object),
            "date": event_date,
        },
    )


def topic_fingerprint(
    primary_category: str,
    entities: Iterable[str],
    event_object: str,
) -> str:
    return _fingerprint(
        "topic",
        {
            "category": primary_category,
            "entities": sorted(normalize_text(entity) for entity in entities),
            "object": normalize_text(event_object),
        },
    )


def viewpoint_fingerprint(summary: str) -> str:
    return _fingerprint("view", {"summary": normalize_text(summary)})


def title_fingerprint(title: str) -> str:
    return _fingerprint("title", {"title": normalize_text(title)})


def visual_fingerprint(concept: str | None) -> str | None:
    if not concept or not normalize_text(concept):
        return None
    return _fingerprint("visual", {"concept": normalize_text(concept)})


def dedup_record_id(event_fp: str) -> str:
    digest = hashlib.sha256(event_fp.encode("utf-8")).hexdigest()[:32]
    return f"dedup-{digest}"


def text_tokens(value: str) -> set[str]:
    """Create mixed Latin tokens and Chinese character bi-grams."""
    normalized = normalize_text(value)
    tokens = set(LATIN_TOKEN_RE.findall(normalized))
    for segment in CJK_RE.findall(normalized):
        if len(segment) == 1:
            tokens.add(segment)
        else:
            tokens.update(segment[index : index + 2] for index in range(len(segment) - 1))
    return tokens


def text_similarity(left: str, right: str) -> float:
    normalized_left = normalize_text(left)
    normalized_right = normalize_text(right)
    if not normalized_left or not normalized_right:
        return 0.0
    if normalized_left == normalized_right:
        return 1.0

    left_tokens = text_tokens(normalized_left)
    right_tokens = text_tokens(normalized_right)
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    sequence = SequenceMatcher(None, normalized_left, normalized_right).ratio()
    return round(max(jaccard, sequence), 4)
