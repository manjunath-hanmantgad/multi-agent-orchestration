"""State and boundary models for procurement workflow."""

from __future__ import annotations

from typing import Any, Optional, TypedDict
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

DECISIONS = {"APPROVED", "REJECTED", "REQUEST_MORE_INFO"}


class ProcurementInput(BaseModel):
    """Validated payload for starting a procurement run."""

    model_config = ConfigDict(extra="forbid")
    workflow_id: str = Field(default_factory=lambda: str(uuid4()))
    vendor_data: dict[str, Any] = Field(default_factory=dict)


class ProcurementOutput(BaseModel):
    """Structured output from procurement workflow runs."""

    model_config = ConfigDict(extra="forbid")
    workflow_id: str
    status: str
    crm_record_id: Optional[str] = None
    due_diligence_result: Optional[dict[str, Any]] = None
    risk_summary: Optional[str] = None
    human_decision: Optional[str] = None
    error: Optional[str] = None


class ProcurementState(TypedDict, total=False):
    """LangGraph state schema for procurement workflow stages."""

    workflow_id: str
    vendor_data: dict[str, Any]
    due_diligence_result: dict[str, Any]
    risk_summary: str
    human_decision: str
    decision_notes: str
    crm_record_id: str
    status: str
    error: str


def build_initial_state(input_data: ProcurementInput) -> ProcurementState:
    """Build initial state from validated input."""
    return {
        "workflow_id": input_data.workflow_id,
        "vendor_data": dict(input_data.vendor_data),
        "status": "PENDING",
    }


def clean_text(value: Any) -> str:
    """Normalize optional text values."""
    return str(value).strip() if value is not None else ""


def required_text(state: ProcurementState, key: str) -> str:
    """Require non-empty string from workflow state."""
    value = clean_text(state.get(key))
    if not value:
        raise ValueError(f"Missing required state field: {key}")
    return value


def next_state(state: ProcurementState, **updates: Any) -> ProcurementState:
    """Create a fresh state dictionary with updates applied."""
    merged: ProcurementState = dict(state)
    merged.update(updates)
    return merged


def decision_value(value: Any) -> str:
    """Validate decision values allowed for procurement review."""
    normalized = clean_text(value).upper()
    if normalized not in DECISIONS:
        raise ValueError(f"human_decision must be one of: {sorted(DECISIONS)}")
    return normalized
