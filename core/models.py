"""Pydantic domain models for workflow data."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkflowStatus(str, Enum):
    """Allowed lifecycle states for workflow runs."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AuditActor(str, Enum):
    """Actors allowed to write audit events."""

    SYSTEM = "SYSTEM"
    HUMAN = "HUMAN"


class WorkflowDecisionValue(str, Enum):
    """Allowed human decision outcomes."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REQUEST_MORE_INFO = "REQUEST_MORE_INFO"


class WorkflowRun(BaseModel):
    """Domain model for a workflow run."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    workflow_type: str = Field(min_length=1)
    status: WorkflowStatus
    current_stage: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class AuditEvent(BaseModel):
    """Domain model for an immutable audit event."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    workflow_id: UUID
    timestamp: datetime
    stage: str = Field(min_length=1)
    actor: AuditActor
    event_type: str = Field(min_length=1)
    event_data: Dict[str, Any] = Field(default_factory=dict)


class WorkflowDecision(BaseModel):
    """Domain model for a workflow decision submission."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: UUID
    actor: AuditActor
    decision: WorkflowDecisionValue
    notes: Optional[str] = None
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
