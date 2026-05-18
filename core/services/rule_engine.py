"""Rule evaluation engine for workflow compliance checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class RuleEngineError(RuntimeError):
    """Raised when rules cannot be loaded or evaluated."""


class RuleEngine:
    """Loads rule definitions and evaluates document fields."""

    def __init__(self, workflows_root: str = "workflows") -> None:
        self._workflows_root = Path(workflows_root)

    def load_rules(self, workflow_name: str) -> list[dict[str, Any]]:
        """Load rules from workflows/<name>/rules.json."""
        rules_path = self._workflows_root / workflow_name / "rules.json"
        if not rules_path.exists():
            raise RuleEngineError(f"Rules file not found: {rules_path}")
        try:
            data = json.loads(rules_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuleEngineError(f"Failed to load rules from: {rules_path}") from exc
        if not isinstance(data, list):
            raise RuleEngineError("Rules file must contain a list of rules")
        return data

    def evaluate(self, document_data: dict[str, Any], rules: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        """Evaluate rule list against document data."""
        if not isinstance(document_data, dict):
            raise RuleEngineError("document_data must be a dictionary")
        outcomes = {"passed": [], "failed": [], "flagged": []}
        for rule in rules:
            outcome = _evaluate_rule(document_data, rule)
            category = _result_category(outcome)
            outcomes[category].append(outcome)
        return outcomes


def _evaluate_rule(document_data: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one rule and return normalized outcome payload."""
    field = str(rule.get("field", "")).strip()
    operator = str(rule.get("operator", "")).strip().lower()
    expected = rule.get("value")
    actual = document_data.get(field)
    passed = _apply_operator(operator, actual, expected)
    return {
        "id": rule.get("id", "unknown"),
        "name": rule.get("name", "unnamed"),
        "description": rule.get("description", ""),
        "field": field,
        "operator": operator,
        "severity": str(rule.get("severity", "medium")),
        "expected": expected,
        "actual": actual,
        "passed": passed,
    }


def _apply_operator(operator: str, actual: Any, expected: Any) -> bool:
    """Apply supported comparison operator."""
    if operator == "equals":
        return actual == expected
    if operator == "contains":
        if isinstance(actual, str):
            return str(expected) in actual
        if isinstance(actual, (list, tuple, set)):
            return expected in actual
        return False
    if operator == "greater_than":
        try:
            return float(actual) > float(expected)
        except (TypeError, ValueError):
            return False
    raise RuleEngineError(f"Unsupported operator: {operator}")


def _result_category(outcome: dict[str, Any]) -> str:
    """Map outcome to passed, failed, or flagged."""
    if outcome["passed"]:
        return "passed"
    severity = str(outcome["severity"]).strip().lower()
    return "flagged" if severity in {"low", "info", "warning"} else "failed"
