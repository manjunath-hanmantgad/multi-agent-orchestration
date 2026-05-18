"""State and boundary models for compliance workflow."""

from __future__ import annotations

from typing import Any, Optional, TypedDict
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from core.services.rule_engine import RuleEngineError

RULE_KEYS = ("id", "name", "description", "field", "operator", "value", "severity")
RULE_OPERATORS = {"equals", "contains", "greater_than"}
RULE_SEVERITIES = {"info", "low", "warning", "medium", "high", "critical"}
DECISIONS = {"APPROVED", "REJECTED", "REQUEST_MORE_INFO"}


class ComplianceReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workflow_id: str = Field(default_factory=lambda: str(uuid4()))
    document_path: str = Field(min_length=1)
    input_fields: dict[str, Any] = Field(default_factory=dict)


class ComplianceReviewOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workflow_id: str
    status: str
    report_path: Optional[str] = None
    risk_score: Optional[int] = None
    risk_reasoning: Optional[str] = None
    human_decision: Optional[str] = None
    decision_notes: Optional[str] = None
    error: Optional[str] = None


class ComplianceReviewState(TypedDict, total=False):
    workflow_id: str
    document_path: str
    input_fields: dict[str, Any]
    extracted_data: dict[str, Any]
    rule_results: dict[str, list[dict[str, Any]]]
    risk_score: int
    risk_reasoning: str
    human_decision: str
    decision_notes: str
    report_path: str
    status: str
    error: str


def build_initial_state(input_data: ComplianceReviewInput) -> ComplianceReviewState:
    return {
        "workflow_id": input_data.workflow_id,
        "document_path": input_data.document_path,
        "input_fields": dict(input_data.input_fields),
        "status": "PENDING",
    }


def clean_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def next_state(state: ComplianceReviewState, **updates: Any) -> ComplianceReviewState:
    merged: ComplianceReviewState = dict(state)
    merged.update(updates)
    return merged


def required_text(state: ComplianceReviewState, key: str) -> str:
    value = clean_text(state.get(key))
    if not value:
        raise ValueError(f"Missing required state field: {key}")
    return value


def build_extracted_data(parsed: dict[str, Any], input_fields: Any) -> dict[str, Any]:
    text = clean_text(parsed.get("text"))
    fields = parse_document_fields(text)
    if isinstance(input_fields, dict):
        fields.update(input_fields)
    fields["full_text"] = text
    metadata = parsed.get("metadata", {}) if isinstance(parsed.get("metadata"), dict) else {}
    return {"text": text, "metadata": metadata, "structured_fields": fields}


def parse_document_fields(text: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        raw_key, raw_value = line.split(":", maxsplit=1)
        key = "_".join(
            part for part in "".join(char if char.isalnum() else "_" for char in raw_key.lower()).split("_") if part
        )
        if key:
            fields[key] = coerce_scalar(raw_value.strip())
    return fields


def coerce_scalar(value: str) -> Any:
    lowered = value.lower()
    if lowered in {"true", "yes", "y"}:
        return True
    if lowered in {"false", "no", "n"}:
        return False
    if value.isdigit():
        return int(value)
    return float(value) if value.replace(".", "", 1).isdigit() and value.count(".") == 1 else value


def rule_payload(state: ComplianceReviewState) -> dict[str, Any]:
    extracted = state.get("extracted_data")
    if not isinstance(extracted, dict):
        raise ValueError("extracted_data is required before rule checks")
    fields = extracted.get("structured_fields")
    if not isinstance(fields, dict):
        raise ValueError("structured_fields must be a dictionary")
    return dict(fields)


def required_results(state: ComplianceReviewState) -> dict[str, list[dict[str, Any]]]:
    results = state.get("rule_results")
    if not isinstance(results, dict):
        raise ValueError("rule_results is required before risk scoring")
    return results


def decision_value(value: Any) -> str:
    normalized = clean_text(value).upper()
    if normalized not in DECISIONS:
        raise ValueError(f"human_decision must be one of: {sorted(DECISIONS)}")
    return normalized


def risk_payload(payload: Any) -> tuple[int, str]:
    if not isinstance(payload, dict):
        raise ValueError("risk scorer must return a dictionary")
    try:
        score = int(payload.get("risk_score"))
    except (TypeError, ValueError) as exc:
        raise ValueError("risk_score must be an integer between 0 and 100") from exc
    reasoning = clean_text(payload.get("risk_reasoning"))
    if score < 0 or score > 100 or not reasoning:
        raise ValueError("risk scorer must return score 0-100 and non-empty reasoning")
    return score, reasoning


def validate_rules(rules: Any) -> list[dict[str, Any]]:
    if not isinstance(rules, list):
        raise RuleEngineError("rules.json must contain a list of rule objects")
    for index, rule in enumerate(rules):
        validate_rule(rule, index)
    return rules


def validate_rule(rule: Any, index: int) -> None:
    if not isinstance(rule, dict):
        raise RuleEngineError(f"Invalid rule schema at index {index}: rule must be an object")
    for key in RULE_KEYS:
        if key not in rule:
            raise RuleEngineError(f"Invalid rule schema at index {index}: missing '{key}'")
    for key in ("id", "name", "description", "field"):
        if not clean_text(rule.get(key)):
            raise RuleEngineError(f"Invalid rule schema at index {index}: '{key}' must not be empty")
    if clean_text(rule["operator"]).lower() not in RULE_OPERATORS:
        raise RuleEngineError(
            f"Invalid rule schema at index {index}: operator must be one of {sorted(RULE_OPERATORS)}"
        )
    if clean_text(rule["severity"]).lower() not in RULE_SEVERITIES:
        raise RuleEngineError(
            f"Invalid rule schema at index {index}: severity must be one of {sorted(RULE_SEVERITIES)}"
        )
