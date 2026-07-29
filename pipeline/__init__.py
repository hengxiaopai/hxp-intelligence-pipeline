"""Core primitives for the HXP Intelligence Pipeline."""

from .dedup import apply_decision, evaluate_candidate
from .normalization import (
    canonicalize_entities,
    event_fingerprint,
    normalize_text,
    topic_fingerprint,
)

__all__ = [
    "apply_decision",
    "canonicalize_entities",
    "evaluate_candidate",
    "event_fingerprint",
    "normalize_text",
    "topic_fingerprint",
    "briefing_assembler",
    "editorial_scoring",
    "failure_reporting",
    "history_commit",
    "scheduler",
]
