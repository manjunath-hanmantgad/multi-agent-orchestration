"""Human decision submission API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies import get_escalation_manager, get_registry, get_state_manager
from core.escalation import EscalationError, HumanEscalationManager
from core.registry import WorkflowNotFoundError, WorkflowRegistry
from core.state import StateError, StateManager

router = APIRouter()
_ALLOWED_DECISIONS = {"APPROVED", "REJECTED", "REQUEST_MORE_INFO"}
_ALLOWED_ACTORS = {"SYSTEM", "HUMAN"}


class WorkflowDecisionRequest(BaseModel):
    """Request body for human workflow decision submission."""

    model_config = ConfigDict(extra="forbid")
    actor: str = Field(min_length=1)
    decision: str = Field(min_length=1)
    notes: str = ""


def _ok(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data, "error": None}


def _validated_decision(value: str) -> str:
    decision = value.strip().upper()
    if decision not in _ALLOWED_DECISIONS:
        allowed = ", ".join(sorted(_ALLOWED_DECISIONS))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid decision. Allowed: {allowed}")
    return decision


def _validated_actor(value: str) -> str:
    actor = value.strip().upper()
    if actor not in _ALLOWED_ACTORS:
        allowed = ", ".join(sorted(_ALLOWED_ACTORS))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid actor. Allowed: {allowed}")
    return actor


async def _get_run_or_404(state_manager: StateManager, workflow_id: str) -> Any:
    try:
        run = await state_manager.get_run(workflow_id)
    except StateError:
        run = None
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return run


def _get_workflow_or_404(workflow_registry: WorkflowRegistry, workflow_type: str) -> Any:
    try:
        return workflow_registry.get(workflow_type)
    except WorkflowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{workflow_id}/decide")
async def submit_decision(
    workflow_id: str,
    request: WorkflowDecisionRequest,
    state_manager: StateManager = Depends(get_state_manager),
    escalation_manager: HumanEscalationManager = Depends(get_escalation_manager),
    workflow_registry: WorkflowRegistry = Depends(get_registry),
) -> dict[str, Any]:
    """Submit decision for paused workflow and resume execution."""
    decision = _validated_decision(request.decision)
    actor = _validated_actor(request.actor)
    run = await _get_run_or_404(state_manager, workflow_id)
    workflow = _get_workflow_or_404(workflow_registry, run.workflow_type)
    try:
        decision_result = await escalation_manager.submit_decision(
            workflow_id=workflow_id,
            actor=actor,
            decision=decision,
            notes=request.notes,
        )
        resume_result = await workflow.resume(workflow_id, decision, request.notes)
    except EscalationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    payload = resume_result.model_dump() if hasattr(resume_result, "model_dump") else dict(resume_result)
    return _ok({"decision": decision_result, "result": payload})
