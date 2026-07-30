"""Shared safety primitives for local browser publishing bridges."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class BrowserBridgeError(ValueError):
    """Raised when a bridge request or result violates HXP safety rules."""


SENSITIVE_QUERY_MARKERS = {
    "access_token",
    "accesstoken",
    "api_key",
    "apikey",
    "auth",
    "authkey",
    "authorization",
    "cookie",
    "csrf",
    "jwt",
    "password",
    "refresh_token",
    "refreshtoken",
    "session",
    "session_id",
    "sessionid",
    "signature",
    "ticket",
    "token",
    "x-amz-signature",
}

SECRET_TEXT_PATTERNS = (
    re.compile(r"(?i)authorization\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)(?:api[_-]?key|token|password|cookie|session)\s*[:=]\s*[^\s,;]+"),
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def redact_sensitive_text(value: str) -> str:
    redacted = str(value)
    for pattern in SECRET_TEXT_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted[:500]


def _normalized_query_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def sanitize_url(value: Any) -> str | None:
    """Return a safe HTTP(S) URL without credentials, fragments or secret query fields."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None

    safe_query: list[tuple[str, str]] = []
    normalized_markers = {_normalized_query_key(marker) for marker in SENSITIVE_QUERY_MARKERS}
    for key, item in parse_qsl(parsed.query, keep_blank_values=True):
        normalized = _normalized_query_key(key)
        if normalized in normalized_markers:
            continue
        if any(marker in normalized for marker in ("token", "secret", "session", "cookie", "signature", "password")):
            continue
        safe_query.append((key, item))

    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(safe_query, doseq=True), "")
    )


def classify_upstream_error(message: Any) -> Mapping[str, Any]:
    """Map an untrusted upstream message to a fail-closed error classification."""
    clean = redact_sensitive_text(str(message or "未知错误"))
    lowered = clean.casefold()

    if any(token in lowered for token in ("captcha", "验证码", "风控", "risk control", "扫码", "qr code")):
        return {
            "code": "BRIDGE_RISK_CONTROL",
            "classification": "risk_control",
            "message": clean,
            "recoverable": False,
        }
    if any(token in lowered for token in ("account mismatch", "identity mismatch", "账号不匹配", "身份不符", "用户不一致")):
        return {
            "code": "BRIDGE_IDENTITY_MISMATCH",
            "classification": "identity",
            "message": clean,
            "recoverable": False,
        }
    if any(token in lowered for token in ("not logged", "login required", "未登录", "登录失效", "unauthorized", "401", "403")):
        return {
            "code": "BRIDGE_AUTH_REQUIRED",
            "classification": "authentication",
            "message": clean,
            "recoverable": True,
        }
    if any(token in lowered for token in ("timeout", "connection", "websocket", "econn", "extension 未连接", "扩展未连接")):
        return {
            "code": "BRIDGE_TRANSPORT_FAILURE",
            "classification": "transport",
            "message": clean,
            "recoverable": True,
        }
    if any(token in lowered for token in ("review", "审核", "人工确认")):
        return {
            "code": "BRIDGE_REVIEW_REQUIRED",
            "classification": "upstream",
            "message": clean,
            "recoverable": False,
        }
    return {
        "code": "BRIDGE_UNKNOWN_FAILURE",
        "classification": "unknown",
        "message": clean,
        "recoverable": False,
    }
