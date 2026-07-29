"""Secret-safe failure reporting with stable fingerprints and issue cooldowns."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from .scheduler import format_datetime, parse_datetime

_SECRET_PATTERNS = [
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+\-/=]+"),
    re.compile(
        r"(?i)\b(token|api[_-]?key|password|passwd|secret|cookie|session)\b"
        r"\s*[:=]\s*([^\s,;]+)"
    ),
    re.compile(r"(?i)(https?://[^\s/:]+:)[^@\s]+@"),
]


def sanitize_message(message: str) -> str:
    """Redact common credentials while preserving enough context to debug."""
    sanitized = str(message).replace("\x00", "")
    sanitized = _SECRET_PATTERNS[0].sub(r"\1[REDACTED]", sanitized)
    sanitized = _SECRET_PATTERNS[1].sub(r"\1[REDACTED]", sanitized)

    def replace_pair(match: re.Match[str]) -> str:
        return f"{match.group(1)}=[REDACTED]"

    sanitized = _SECRET_PATTERNS[2].sub(replace_pair, sanitized)
    sanitized = _SECRET_PATTERNS[3].sub(r"\1[REDACTED]@", sanitized)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized[:1000] or "[EMPTY ERROR MESSAGE]"


def _fingerprint(
    *,
    stage: str,
    error_type: str,
    message: str,
    source_registry_id: str | None,
) -> str:
    normalized = "|".join(
        [
            stage.strip().lower(),
            error_type.strip().lower(),
            message.strip().lower(),
            (source_registry_id or "").strip().lower(),
        ]
    )
    return "failure-" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def build_failure_report(
    *,
    occurred_at: datetime,
    stage: str,
    error_type: str,
    message: str,
    config: Mapping[str, Any],
    prior_reports: Iterable[Mapping[str, Any]] = (),
    run_id: str | None = None,
    source_registry_id: str | None = None,
    retryable: bool = True,
    issue_enabled: bool = False,
    context: Mapping[str, str | int | float | bool | None] | None = None,
) -> dict[str, Any]:
    if occurred_at.tzinfo is None:
        raise ValueError("occurred_at 必须包含时区")
    observed = occurred_at.astimezone(timezone.utc)
    sanitized = sanitize_message(message)
    fingerprint = _fingerprint(
        stage=stage,
        error_type=error_type,
        message=sanitized,
        source_registry_id=source_registry_id,
    )

    matching = [
        report
        for report in prior_reports
        if report.get("fingerprint") == fingerprint
    ]
    occurrence_count = len(matching) + 1
    cooldown_hours = int(config["failure_issue_cooldown_hours"])
    recent_cutoff = observed - timedelta(hours=cooldown_hours)
    cooldown_active = any(
        parse_datetime(str(report["occurred_at"])) >= recent_cutoff
        for report in matching
        if report.get("occurred_at")
    )
    issue_eligible = bool(issue_enabled and not cooldown_active)

    next_retry_at = None
    if retryable:
        next_retry_at = format_datetime(
            observed + timedelta(minutes=int(config["failure_retry_minutes"]))
        )

    report: dict[str, Any] = {
        "schema_version": "1.0.0",
        "failure_id": fingerprint,
        "occurred_at": format_datetime(observed),
        "stage": stage,
        "error_type": error_type[:100],
        "message": sanitized,
        "fingerprint": fingerprint,
        "run_id": run_id,
        "source_registry_id": source_registry_id,
        "retryable": bool(retryable),
        "next_retry_at": next_retry_at,
        "occurrence_count": occurrence_count,
        "issue_eligible": issue_eligible,
        "secrets_redacted": True,
    }
    if context:
        report["context"] = dict(list(context.items())[:20])
    return report
