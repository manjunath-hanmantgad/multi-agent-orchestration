"""SQLAlchemy ORM schema definitions for platform tables."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


WORKFLOW_STATUS_ENUM = Enum(
    "PENDING",
    "RUNNING",
    "PAUSED",
    "APPROVED",
    "REJECTED",
    "COMPLETED",
    "FAILED",
    name="workflow_run_status",
    native_enum=False,
)

ACTOR_ENUM = Enum("SYSTEM", "HUMAN", name="audit_actor", native_enum=False)


class Base(DeclarativeBase):
    """Declarative base class for all ORM tables."""


def utcnow() -> datetime:
    """Generate UTC timestamps in application code for SQLite compatibility."""
    return datetime.now(timezone.utc)


class WorkflowRunORM(Base):
    """Persistent workflow run state."""

    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workflow_type: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(WORKFLOW_STATUS_ENUM, nullable=False)
    current_stage: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    audit_events: Mapped[List["AuditEventORM"]] = relationship(back_populates="workflow")
    crm_records: Mapped[List["CRMRecordORM"]] = relationship(back_populates="workflow")


class AuditEventORM(Base):
    """Immutable event log entries for workflow actions."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_runs.id"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    stage: Mapped[str] = mapped_column(String(120), nullable=False)
    actor: Mapped[str] = mapped_column(ACTOR_ENUM, nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    event_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    workflow: Mapped[WorkflowRunORM] = relationship(back_populates="audit_events")


class CRMRecordORM(Base):
    """Procurement decisions mirrored into mock CRM records."""

    __tablename__ = "crm_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_runs.id"), nullable=False
    )
    vendor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    decision: Mapped[str] = mapped_column(String(50), nullable=False)
    decision_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    workflow: Mapped[WorkflowRunORM] = relationship(back_populates="crm_records")
