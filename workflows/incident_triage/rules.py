"""Severity classification rules for incident triage.

Deterministic logic mapping LLM severity output to P1/P2/P3/P4 levels.
No LLM calls here — only string matching and classification constants.
"""

from __future__ import annotations

from typing import Any

SEVERITY_LEVELS = ("P1", "P2", "P3", "P4")
VALID_SEVERITY_VALUES = {"critical", "high", "medium", "low", "info", "p1", "p2", "p3", "p4", "1", "2", "3", "4"}

SEVERITY_MAP: dict[str, str] = {
    "critical": "P1",
    "high": "P2",
    "medium": "P3",
    "low": "P4",
    "info": "P4",
    "p1": "P1",
    "p2": "P2",
    "p3": "P3",
    "p4": "P4",
    "1": "P1",
    "2": "P2",
    "3": "P3",
    "4": "P4",
}

HIGH_SEVERITY = {"P1", "P2"}
LOW_SEVERITY = {"P3", "P4"}


def classify_severity(severity_label: str) -> str:
    """Map a raw severity label to a P1-P4 level.

    Accepts: 'critical', 'high', 'medium', 'low', 'p1'-'p4', '1'-'4'.
    Raises ValueError for unrecognised labels — never silently defaults.
    """
    key = severity_label.strip().lower()
    if key not in SEVERITY_MAP:
        raise ValueError(
            f"Unrecognised severity label: {severity_label!r}. "
            f"Valid labels: {sorted(VALID_SEVERITY_VALUES)}"
        )
    return SEVERITY_MAP[key]


def is_high_severity(severity_level: str) -> bool:
    """Return True if the severity level requires human approval (P1/P2)."""
    return classify_severity(severity_level) in HIGH_SEVERITY


def is_low_severity(severity_level: str) -> bool:
    """Return True if the severity level auto-resolves (P3/P4)."""
    return classify_severity(severity_level) in LOW_SEVERITY


def severity_payload(result: dict[str, Any]) -> tuple[str, str]:
    """Validate and extract severity classification payload.

    Expects a dict with keys:
      - severity_level (str): one of P1-P4
      - reasoning (str): non-empty explanation
    Returns (severity_level, reasoning) on success.
    Raises ValueError on invalid input.
    """
    if not isinstance(result, dict):
        raise ValueError("severity scorer must return a dictionary")
    try:
        level = str(result.get("severity_level", ""))
    except (TypeError, ValueError) as exc:
        raise ValueError("severity_level must be a string") from exc
    level = classify_severity(level)
    reasoning = clean_text(result.get("reasoning"))
    if level not in SEVERITY_LEVELS or not reasoning:
        raise ValueError("severity scorer must return a valid P1-P4 level and non-empty reasoning")
    return level, reasoning


def clean_text(value: Any) -> str:
    """Normalise optional text values."""
    return str(value).strip() if value is not None else ""
