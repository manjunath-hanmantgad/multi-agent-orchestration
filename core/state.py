"""State management for workflow checkpoints and run status."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.models import WorkflowRun, WorkflowStatus
from core.schemas import WorkflowRunORM

logger = logging.getLogger(__name__)


class StateError(RuntimeError):
    """Raised when workflow state operations fail."""


class StateManager:
    """Persists workflow checkpoints and high-level run state."""

    def __init__(
        self,
        database_url: str | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._session_factory = _resolve_session_factory(database_url, session_factory)
        self._lock = asyncio.Lock()

    async def save_checkpoint(self, workflow_id: str, checkpoint_data: dict[str, Any]) -> None:
        """Upsert checkpoint payload data into workflow_runs."""
        normalized_id = _validate_uuid(workflow_id)
        if not isinstance(checkpoint_data, dict):
            raise StateError("checkpoint_data must be a dictionary")
        async with self._lock:
            await self._upsert_checkpoint(normalized_id, checkpoint_data)

    async def load_checkpoint(self, workflow_id: str) -> dict[str, Any] | None:
        """Load checkpoint data for workflow or return None."""
        normalized_id = _validate_uuid(workflow_id)
        run = await self._get_run_row(normalized_id)
        if run is None or not isinstance(run.payload, dict):
            return None
        checkpoint = run.payload.get("checkpoint_data")
        return checkpoint if isinstance(checkpoint, dict) else None

    async def update_status(self, workflow_id: str, status: str, stage: str | None) -> None:
        """Update workflow status/stage for an existing run only."""
        normalized_id = _validate_uuid(workflow_id)
        normalized_status = _validate_status(status)
        normalized_stage = stage.strip() if isinstance(stage, str) and stage.strip() else None
        async with self._lock:
            await self._apply_status_update(normalized_id, normalized_status, normalized_stage)

    async def get_run(self, workflow_id: str) -> WorkflowRun | None:
        """Get workflow run as Pydantic model or None."""
        normalized_id = _validate_uuid(workflow_id)
        row = await self._get_run_row(normalized_id)
        return _to_model(row) if row else None

    async def list_runs_by_status(self, status: str) -> list[WorkflowRun]:
        """List runs that match a specific workflow status."""
        normalized_status = _validate_status(status)
        try:
            async with self._session_factory() as session:
                result = await session.execute(
                    select(WorkflowRunORM)
                    .where(WorkflowRunORM.status == normalized_status)
                    .order_by(WorkflowRunORM.created_at.asc())
                )
                rows = result.scalars().all()
        except SQLAlchemyError as exc:
            logger.exception(
                "state_list_by_status_failed workflow_id=%s stage=%s error_type=%s",
                "-",
                "list_runs_by_status",
                type(exc).__name__,
            )
            raise StateError("Failed to list workflow runs by status") from exc
        return [_to_model(row) for row in rows]

    async def _upsert_checkpoint(self, workflow_id: str, checkpoint_data: dict[str, Any]) -> None:
        """Internal checkpoint upsert with merge semantics."""
        try:
            async with self._session_factory() as session:
                row = await session.get(WorkflowRunORM, workflow_id)
                if row is None:
                    row = _new_run(workflow_id, checkpoint_data)
                    session.add(row)
                else:
                    row.payload = _merged_payload(row.payload, checkpoint_data)
                    row.updated_at = _utcnow()
                await session.commit()
        except SQLAlchemyError as exc:
            logger.exception(
                "state_save_checkpoint_failed workflow_id=%s stage=%s error_type=%s",
                workflow_id,
                "checkpoint",
                type(exc).__name__,
            )
            raise StateError("Failed to save checkpoint") from exc

    async def _apply_status_update(self, workflow_id: str, status: str, stage: str | None) -> None:
        """Internal status update for existing rows only."""
        try:
            async with self._session_factory() as session:
                row = await session.get(WorkflowRunORM, workflow_id)
                if row is None:
                    raise StateError(f"Workflow run not found: {workflow_id}")
                row.status = status
                row.current_stage = stage
                row.updated_at = _utcnow()
                await session.commit()
        except StateError:
            raise
        except SQLAlchemyError as exc:
            logger.exception(
                "state_update_status_failed workflow_id=%s stage=%s error_type=%s",
                workflow_id,
                stage or "-",
                type(exc).__name__,
            )
            raise StateError("Failed to update workflow status") from exc

    async def _get_run_row(self, workflow_id: str) -> WorkflowRunORM | None:
        """Fetch run ORM row by workflow id."""
        try:
            async with self._session_factory() as session:
                return await session.get(WorkflowRunORM, workflow_id)
        except SQLAlchemyError as exc:
            logger.exception(
                "state_get_run_failed workflow_id=%s stage=%s error_type=%s",
                workflow_id,
                "get_run",
                type(exc).__name__,
            )
            raise StateError("Failed to fetch workflow run") from exc


def _resolve_session_factory(
    database_url: str | None,
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> async_sessionmaker[AsyncSession]:
    """Resolve async session factory from arguments or shared database layer."""
    if session_factory is not None:
        return session_factory
    if database_url:
        engine = create_async_engine(database_url, echo=False)
        return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    from core.database import AsyncSessionLocal

    return AsyncSessionLocal


def _validate_uuid(workflow_id: str) -> str:
    """Validate and normalize workflow id string."""
    try:
        return str(UUID(workflow_id))
    except (TypeError, ValueError) as exc:
        raise StateError("workflow_id must be a valid UUID") from exc


def _validate_status(status: str) -> str:
    """Validate workflow status against enum values."""
    try:
        return WorkflowStatus(status).value
    except ValueError as exc:
        allowed = ", ".join(item.value for item in WorkflowStatus)
        raise StateError(f"Invalid workflow status: {status}. Allowed: {allowed}") from exc


def _merged_payload(existing: dict[str, Any] | None, checkpoint_data: dict[str, Any]) -> dict[str, Any]:
    """Return merged payload preserving non-checkpoint keys."""
    payload: dict[str, Any] = dict(existing or {})
    previous = payload.get("checkpoint_data")
    merged_checkpoint = dict(previous or {}) if isinstance(previous, dict) else {}
    merged_checkpoint.update(checkpoint_data)
    payload["checkpoint_data"] = merged_checkpoint
    return payload


def _new_run(workflow_id: str, checkpoint_data: dict[str, Any]) -> WorkflowRunORM:
    """Build new workflow row from checkpoint payload."""
    workflow_type = checkpoint_data.get("workflow_type") or "unknown"
    status = checkpoint_data.get("status") or WorkflowStatus.RUNNING.value
    return WorkflowRunORM(
        id=workflow_id,
        workflow_type=str(workflow_type),
        status=_validate_status(str(status)),
        current_stage=checkpoint_data.get("stage"),
        payload={"checkpoint_data": dict(checkpoint_data)},
    )


def _to_model(row: WorkflowRunORM) -> WorkflowRun:
    """Convert ORM row to WorkflowRun domain model."""
    return WorkflowRun(
        id=row.id,
        workflow_type=row.workflow_type,
        status=row.status,
        current_stage=row.current_stage,
        payload=row.payload or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _utcnow() -> datetime:
    """Return current UTC timestamp."""
    return datetime.now(timezone.utc)
