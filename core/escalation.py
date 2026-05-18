"""Human escalation manager for pause/resume workflow control."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.audit import AuditLogger
from core.state import StateError, StateManager

_ALLOWED_DECISIONS = {"APPROVED", "REJECTED", "REQUEST_MORE_INFO"}


class EscalationError(RuntimeError):
    """Raised when escalation operations fail validation or persistence."""


class HumanEscalationManager:
    """Manages human review request and decision lifecycle."""

    def __init__(
        self,
        state_manager: StateManager | None = None,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self._state_manager = state_manager or StateManager()
        self._audit_logger = audit_logger or AuditLogger()

    async def request_review(self, workflow_id: str, context: dict[str, Any]) -> None:
        """Pause workflow and store review context for human approval."""
        if not isinstance(context, dict):
            raise EscalationError("context must be a dictionary")
        checkpoint = await self._state_manager.load_checkpoint(workflow_id) or {}
        checkpoint.update(
            {
                "review_context": context,
                "review_requested_at": _utcnow_iso(),
            }
        )
        await _wrap_state_call(self._state_manager.save_checkpoint(workflow_id, checkpoint))
        await _wrap_state_call(
            self._state_manager.update_status(workflow_id, "PAUSED", "human_review")
        )
        await self._audit_logger.log(
            workflow_id,
            "human_review",
            "SYSTEM",
            "REVIEW_REQUESTED",
            {"context": context},
        )

    async def submit_decision(
        self,
        workflow_id: str,
        actor: str,
        decision: str,
        notes: str | None,
    ) -> dict[str, str]:
        """Store human decision and move workflow into the next status."""
        normalized_decision = _validate_decision(decision)
        normalized_actor = _validate_actor(actor)
        run = await _wrap_state_result(self._state_manager.get_run(workflow_id))
        if run is None:
            raise EscalationError(f"Workflow not found: {workflow_id}")

        checkpoint = await self._state_manager.load_checkpoint(workflow_id) or {}
        checkpoint.update(
            {
                "human_decision": normalized_decision,
                "decision_notes": notes or "",
                "decision_actor": normalized_actor,
                "decided_at": _utcnow_iso(),
            }
        )
        await _wrap_state_call(self._state_manager.save_checkpoint(workflow_id, checkpoint))

        next_status = "RUNNING" if normalized_decision == "REQUEST_MORE_INFO" else normalized_decision
        await _wrap_state_call(self._state_manager.update_status(workflow_id, next_status, "decision"))
        await self._audit_logger.log(
            workflow_id,
            "decision",
            normalized_actor,
            "DECISION_SUBMITTED",
            {"decision": normalized_decision, "notes": notes or ""},
        )
        return {"workflow_id": workflow_id, "status": next_status, "decision": normalized_decision}

    async def get_pending_reviews(self) -> list[dict[str, Any]]:
        """Return paused workflow runs waiting for human action."""
        runs = await _wrap_state_result(self._state_manager.list_runs_by_status("PAUSED"))
        pending: list[dict[str, Any]] = []
        for run in runs:
            checkpoint = run.payload.get("checkpoint_data", {}) if isinstance(run.payload, dict) else {}
            pending.append(
                {
                    "workflow_id": str(run.id),
                    "workflow_type": run.workflow_type,
                    "status": run.status.value if hasattr(run.status, "value") else str(run.status),
                    "current_stage": run.current_stage,
                    "review_context": checkpoint.get("review_context", {}),
                }
            )
        return pending


def _validate_decision(decision: str) -> str:
    """Validate human decision against supported values."""
    normalized = (decision or "").strip().upper()
    if normalized not in _ALLOWED_DECISIONS:
        allowed = ", ".join(sorted(_ALLOWED_DECISIONS))
        raise EscalationError(f"Invalid decision: {decision}. Allowed: {allowed}")
    return normalized


def _validate_actor(actor: str) -> str:
    """Validate audit actor for decision submission."""
    normalized = (actor or "").strip().upper()
    if normalized not in {"SYSTEM", "HUMAN"}:
        raise EscalationError("actor must be one of: SYSTEM, HUMAN")
    return normalized


def _utcnow_iso() -> str:
    """Return UTC datetime string for state checkpoint fields."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


async def _wrap_state_call(coro: Any) -> None:
    """Map state manager errors into escalation errors."""
    try:
        await coro
    except StateError as exc:
        raise EscalationError(str(exc)) from exc


async def _wrap_state_result(coro: Any) -> Any:
    """Map state manager errors into escalation errors and return result."""
    try:
        return await coro
    except StateError as exc:
        raise EscalationError(str(exc)) from exc
