"""Workflow lifecycle API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import (
    get_db_session,
    get_escalation_manager,
    get_registry,
)
from core.escalation import HumanEscalationManager
from core.registry import WorkflowNotFoundError, WorkflowRegistry
from core.schemas import WorkflowRunORM

router = APIRouter()


class WorkflowStartRequest(BaseModel):
    """Request body for starting workflows."""

    model_config = ConfigDict(extra="forbid")
    workflow_type: str = Field(min_length=1)
    input_data: dict[str, Any] = Field(default_factory=dict)


def _ok(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data, "error": None}


def _serialize_run(run: WorkflowRunORM) -> dict[str, Any]:
    return {
        "id": run.id,
        "workflow_type": run.workflow_type,
        "status": run.status,
        "current_stage": run.current_stage,
        "payload": run.payload or {},
        "created_at": _ts(run.created_at),
        "updated_at": _ts(run.updated_at),
    }


def _ts(value: datetime | None) -> str:
    return value.isoformat() if isinstance(value, datetime) else ""


@router.post("/start")
async def start_workflow(
    request: WorkflowStartRequest,
    workflow_registry: WorkflowRegistry = Depends(get_registry),
) -> dict[str, Any]:
    """Start a workflow run by type and input payload."""
    try:
        workflow = workflow_registry.get(request.workflow_type)
    except WorkflowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if not hasattr(workflow, "start"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Workflow does not support start(): {request.workflow_type}",
        )
    result = await workflow.start(request.input_data)
    payload = result.model_dump() if hasattr(result, "model_dump") else dict(result)
    workflow_id = payload.get("workflow_id") or request.input_data.get("workflow_id")
    return _ok({"workflow_id": workflow_id, "result": payload})


@router.get("")
async def list_workflows(session: AsyncSession = Depends(get_db_session)) -> dict[str, Any]:
    """List workflow runs with status and stage metadata."""
    result = await session.execute(
        select(WorkflowRunORM).order_by(WorkflowRunORM.created_at.desc())
    )
    rows = result.scalars().all()
    return _ok([_serialize_run(row) for row in rows])


@router.get("/pending")
async def list_pending_reviews(
    escalation_manager: HumanEscalationManager = Depends(get_escalation_manager),
) -> dict[str, Any]:
    """List paused workflow runs pending human review."""
    pending = await escalation_manager.get_pending_reviews()
    return _ok(pending)


@router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Get full workflow run details by id."""
    row = await session.get(WorkflowRunORM, workflow_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return _ok(_serialize_run(row))
