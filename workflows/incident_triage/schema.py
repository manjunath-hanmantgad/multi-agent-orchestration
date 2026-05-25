"""State and boundary models for incident triage workflow."""

from __future__ import annotations

from typing import Any, Optional, TypedDict
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

DECISIONS = {"APPROVED", "REJECTED", "REQUEST_MORE_INFO"}


class IncidentTriageInput(BaseModel):
    """Validated payload for starting an incident triage run."""

    model_config = ConfigDict(extra="forbid")
    workflow_id: str = Field(default_factory=lambda: str(uuid4()))
    incident_text: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    severity_level: Optional[str] = None


class IncidentTriageOutput(BaseModel):
    """Structured output from incident triage workflow runs."""

    model_config = ConfigDict(extra="forbid")
    workflow_id: str
    status: str
    severity_level: Optional[str] = None
    severity_reasoning: Optional[str] = None
    resolution_report: Optional[str] = None
    human_decision: Optional[str] = None
    decision_notes: Optional[str] = None
    error: Optional[str] = None


class IncidentTriageState(TypedDict, total=False):
    """LangGraph state schema for incident triage workflow stages."""

    workflow_id: str
    incident_text: str
    metadata: dict[str, Any]
    severity_level: str
    severity_reasoning: str
    human_decision: str
    decision_notes: str
    resolution_report: str
    status: str
    error: str


def build_initial_state(input_data: IncidentTriageInput) -> IncidentTriageState:
    """Build initial state from validated input."""
    state: IncidentTriageState = {
        "workflow_id": input_data.workflow_id,
        "incident_text": input_data.incident_text,
        "metadata": dict(input_data.metadata),
        "status": "PENDING",
    }
    if input_data.severity_level is not None:
        state["severity_level"] = input_data.severity_level
    return state


def clean_text(value: Any) -> str:
    """Normalise optional text values."""
    return str(value).strip() if value is not None else ""


def next_state(state: IncidentTriageState, **updates: Any) -> IncidentTriageState:
    """Create a fresh state dictionary with updates applied."""
    merged: IncidentTriageState = dict(state)
    merged.update(updates)
    return merged


def required_text(state: IncidentTriageState, key: str) -> str:
    """Require non-empty string from workflow state."""
    value = clean_text(state.get(key))
    if not value:
        raise ValueError(f"Missing required state field: {key}")
    return value


def decision_value(value: Any) -> str:
    """Validate decision values allowed for incident triage review."""
    normalized = clean_text(value).upper()
    if normalized not in DECISIONS:
        raise ValueError(f"human_decision must be one of: {sorted(DECISIONS)}")
    return normalized
