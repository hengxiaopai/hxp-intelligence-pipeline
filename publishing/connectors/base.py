"""Shared deterministic helpers for connector authorization and execution."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Mapping


class ConnectorError(ValueError):
    """Base error for connector validation and execution failures."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def parse_timestamp(value: str, *, field: str) -> datetime:
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ConnectorError(f"{field}不是有效ISO-8601时间：{value}") from exc
    if parsed.tzinfo is None:
        raise ConnectorError(f"{field}必须包含时区：{value}")
    return parsed


def ordered_hashes(value: Any) -> list[str]:
    hashes = [str(item) for item in value]
    if not hashes or any(len(item) != 64 for item in hashes):
        raise ConnectorError("图片哈希必须是非空的64位SHA-256列表")
    if len(set(hashes)) != len(hashes):
        raise ConnectorError("图片哈希列表不能重复")
    return hashes


def safe_credential_reference(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("env:"):
        name = text[4:]
        if not name or not name.replace("_", "").isalnum() or name.upper() != name:
            raise ConnectorError("环境变量凭据引用格式无效")
        return text
    if text.startswith("secret:"):
        reference = text[7:]
        if len(reference) < 3 or any(character.isspace() for character in reference):
            raise ConnectorError("秘密存储引用格式无效")
        return text
    raise ConnectorError("只允许env:或secret:凭据引用，禁止保存凭据值")


def exact_binding(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "entry_id": str(entry["entry_id"]),
        "idempotency_key": str(entry["idempotency_key"]),
        "content_hash": str(entry["content_hash"]),
        "asset_hashes": ordered_hashes(entry["asset_hashes"]),
        "action": str(entry["action"]),
        "platform": str(entry["platform"]),
    }
