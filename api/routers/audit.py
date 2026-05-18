"""Audit trail retrieval API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import get_audit_logger, get_state_manager
from core.audit import AuditError, AuditLogger
from core.state import StateError, StateManager

router = APIRouter()


def _ok(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data, "error": None}


@router.get("/{workflow_id}/audit")
async def get_audit_trail(
    workflow_id: str,
    state_manager: StateManager = Depends(get_state_manager),
    audit_logger: AuditLogger = Depends(get_audit_logger),
) -> dict[str, Any]:
    """Return ordered audit trail for a workflow id."""
    try:
        run = await state_manager.get_run(workflow_id)
    except StateError:
        run = None
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    try:
        trail = await audit_logger.get_trail(workflow_id)
    except AuditError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _ok(trail)
