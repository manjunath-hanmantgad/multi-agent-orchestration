"""Immutable append-only audit logging."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.schemas import AuditEventORM, WorkflowRunORM

logger = logging.getLogger(__name__)
_ALLOWED_ACTORS = {"SYSTEM", "HUMAN"}


class AuditError(RuntimeError):
    """Raised when audit operations fail validation or persistence."""


class AuditLogger:
    """Append-only audit trail logger backed by async SQLAlchemy sessions."""

    def __init__(
        self,
        database_url: str | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._session_factory = _resolve_session_factory(database_url, session_factory)
        self._lock = asyncio.Lock()

    async def log(
        self,
        workflow_id: str,
        stage: str,
        actor: str,
        event_type: str,
        data: dict[str, Any] | None,
    ) -> None:
        """Append an immutable audit event for a workflow."""
        normalized = _normalize_event_input(workflow_id, stage, actor, event_type, data)
        async with self._lock:
            await self._append_event(normalized)

    async def get_trail(self, workflow_id: str) -> list[dict[str, Any]]:
        """Return all audit events ordered by timestamp for the given workflow."""
        normalized_workflow_id = _validate_uuid(workflow_id, "workflow_id")
        try:
            async with self._session_factory() as session:
                result = await session.execute(
                    select(AuditEventORM)
                    .where(AuditEventORM.workflow_id == normalized_workflow_id)
                    .order_by(AuditEventORM.timestamp.asc(), AuditEventORM.id.asc())
                )
                rows = result.scalars().all()
        except SQLAlchemyError as exc:
            logger.exception(
                "audit_trail_fetch_failed workflow_id=%s stage=%s error_type=%s",
                normalized_workflow_id,
                "audit_trail",
                type(exc).__name__,
            )
            raise AuditError("Failed to fetch audit trail") from exc
        return [_event_to_dict(row) for row in rows]

    async def _append_event(self, normalized: dict[str, Any]) -> None:
        """Persist a validated audit event as an append-only row."""
        try:
            async with self._session_factory() as session:
                if not await _workflow_exists(session, normalized["workflow_id"]):
                    raise AuditError(f"Invalid workflow_id: {normalized['workflow_id']}")
                session.add(_build_event_row(normalized))
                await session.commit()
        except AuditError:
            raise
        except SQLAlchemyError as exc:
            logger.exception(
                "audit_log_failed workflow_id=%s stage=%s error_type=%s",
                normalized["workflow_id"],
                normalized["stage"],
                type(exc).__name__,
            )
            raise AuditError("Failed to persist audit event") from exc


def _resolve_session_factory(
    database_url: str | None,
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> async_sessionmaker[AsyncSession]:
    """Resolve session factory from explicit factory, URL, or shared DB layer."""
    if session_factory is not None:
        return session_factory
    if database_url:
        engine = create_async_engine(database_url, echo=False)
        return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return _default_session_factory()


def _default_session_factory() -> async_sessionmaker[AsyncSession]:
    """Load shared session factory lazily from core.database."""
    from core.database import AsyncSessionLocal

    return AsyncSessionLocal


def _validate_uuid(value: str, field_name: str) -> str:
    """Validate UUID inputs and return normalized string value."""
    try:
        return str(UUID(value))
    except (TypeError, ValueError) as exc:
        raise AuditError(f"{field_name} must be a valid UUID") from exc


def _require_text(value: str, field_name: str) -> str:
    """Ensure required text input is non-empty after trimming."""
    cleaned = (value or "").strip()
    if not cleaned:
        raise AuditError(f"{field_name} must not be empty")
    return cleaned


def _validate_actor(actor: str) -> str:
    """Validate audit actor values against allowed constants."""
    normalized = _require_text(actor, "actor").upper()
    if normalized not in _ALLOWED_ACTORS:
        raise AuditError("actor must be one of: SYSTEM, HUMAN")
    return normalized


def _normalize_event_input(
    workflow_id: str,
    stage: str,
    actor: str,
    event_type: str,
    data: dict[str, Any] | None,
) -> dict[str, Any]:
    """Validate and normalize audit event input fields."""
    return {
        "workflow_id": _validate_uuid(workflow_id, "workflow_id"),
        "stage": _require_text(stage, "stage"),
        "actor": _validate_actor(actor),
        "event_type": _require_text(event_type, "event_type"),
        "event_data": data or {},
    }


def _build_event_row(normalized: dict[str, Any]) -> AuditEventORM:
    """Build ORM row for audit event insertion."""
    return AuditEventORM(
        id=str(uuid4()),
        workflow_id=normalized["workflow_id"],
        timestamp=datetime.now(timezone.utc),
        stage=normalized["stage"],
        actor=normalized["actor"],
        event_type=normalized["event_type"],
        event_data=normalized["event_data"],
    )


async def _workflow_exists(session: AsyncSession, workflow_id: str) -> bool:
    """Check if workflow row exists before appending an audit event."""
    result = await session.execute(
        select(WorkflowRunORM.id).where(WorkflowRunORM.id == workflow_id).limit(1)
    )
    return result.scalar_one_or_none() is not None


def _event_to_dict(row: AuditEventORM) -> dict[str, Any]:
    """Convert ORM row into API-friendly audit event dictionary."""
    return {
        "id": row.id,
        "workflow_id": row.workflow_id,
        "timestamp": row.timestamp.isoformat() if row.timestamp else "",
        "stage": row.stage,
        "actor": row.actor,
        "event_type": row.event_type,
        "event_data": row.event_data or {},
    }
