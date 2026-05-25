"""Agent nodes for incident triage workflow execution."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

from core.audit import AuditLogger
from core.escalation import HumanEscalationManager
from core.state import StateManager
from workflows.incident_triage.rules import classify_severity
from workflows.incident_triage.schema import (
    IncidentTriageState,
    clean_text,
    decision_value,
    next_state,
    required_text,
)

logger = logging.getLogger(__name__)


class IncidentTriageError(RuntimeError):
    """Raised when workflow stage execution fails."""


class IncidentTriageAgents:
    """Node handlers with persistence and audit side effects."""

    def __init__(
        self,
        *,
        state_manager: StateManager | None = None,
        audit_logger: AuditLogger | None = None,
        escalation_manager: HumanEscalationManager | None = None,
        severity_scorer: Callable[[str], Any] | None = None,
    ) -> None:
        self._state = state_manager or StateManager()
        self._audit = audit_logger or AuditLogger()
        self._escalation = escalation_manager or HumanEscalationManager(
            state_manager=self._state,
            audit_logger=self._audit,
        )
        self._severity_scorer = severity_scorer

    async def intake_node(self, state: IncidentTriageState) -> IncidentTriageState:
        """Extract incident text and metadata into state."""
        workflow_id, stage = _require(state, "workflow_id"), "intake"
        try:
            incident_text = _require(state, "incident_text")
            updates = next_state(state, status="RUNNING", error=None)
            await self._persist(workflow_id, stage, updates)
            await self._audit.log(
                workflow_id,
                stage,
                "SYSTEM",
                "STAGE_COMPLETED",
                {"incident_length": len(incident_text), "metadata_keys": sorted(state.get("metadata", {}).keys())},
            )
            return updates
        except (IncidentTriageError, ValueError) as exc:
            return await self._fail(workflow_id, stage, state, exc)

    async def severity_assessment_node(self, state: IncidentTriageState) -> IncidentTriageState:
        """LLM call to classify incident severity as P1-P4 with structured reasoning."""
        workflow_id, stage = _require(state, "workflow_id"), "severity_assessment"
        try:
            level, reasoning = await self._assess_severity(state)
            updates = next_state(
                state,
                severity_level=level,
                severity_reasoning=reasoning,
                status="RUNNING",
                error=None,
            )
            await self._persist(workflow_id, stage, updates)
            await self._audit.log(
                workflow_id,
                stage,
                "SYSTEM",
                "STAGE_COMPLETED",
                {"severity_level": level, "severity_reasoning": reasoning},
            )
            return updates
        except (IncidentTriageError, ValueError) as exc:
            return await self._fail(workflow_id, stage, state, exc)

    async def escalation_decision_node(self, state: IncidentTriageState) -> IncidentTriageState:
        """Rule-based routing: set status based on severity level."""
        workflow_id, stage = _require(state, "workflow_id"), "escalation_decision"
        try:
            severity_level = classify_severity(_require(state, "severity_level"))
            needs_human = severity_level in ("P1", "P2")
            status = "RUNNING" if needs_human else "COMPLETED"
            updates = next_state(state, severity_level=severity_level, status=status, error=None)
            await self._persist(workflow_id, stage, updates)
            await self._audit.log(
                workflow_id,
                stage,
                "SYSTEM",
                "STAGE_COMPLETED",
                {
                    "severity_level": severity_level,
                    "needs_human_approval": needs_human,
                    "status": status,
                },
            )
            return updates
        except (IncidentTriageError, ValueError) as exc:
            return await self._fail(workflow_id, stage, state, exc)

    async def human_approval_node(self, state: IncidentTriageState) -> IncidentTriageState:
        """Pause workflow for human review of P1/P2 incidents."""
        workflow_id, stage = _require(state, "workflow_id"), "human_approval"
        try:
            incident_text = state.get("incident_text", "")
            metadata = state.get("metadata", {})
            context = {
                "severity_level": state.get("severity_level"),
                "severity_reasoning": state.get("severity_reasoning"),
                "incident_preview": incident_text[:500] if isinstance(incident_text, str) else "",
                "metadata_keys": sorted(key for key in metadata.keys()) if isinstance(metadata, dict) else [],
            }
            await self._escalation.request_review(workflow_id, context)
            updates = next_state(state, status="PAUSED", error=None)
            await self._persist(workflow_id, stage, updates)
            await self._audit.log(
                workflow_id,
                stage,
                "SYSTEM",
                "STAGE_COMPLETED",
                {"review_context_keys": sorted(context.keys())},
            )
            return updates
        except (IncidentTriageError, ValueError) as exc:
            return await self._fail(workflow_id, stage, state, exc)

    async def resolution_report_node(self, state: IncidentTriageState) -> IncidentTriageState:
        """Generate structured resolution report after triage completion."""
        workflow_id, stage = _require(state, "workflow_id"), "resolution_report"
        try:
            report = await self._generate_report(state)
            updates = next_state(state, resolution_report=report, status="COMPLETED", error=None)
            await self._persist(workflow_id, stage, updates)
            await self._audit.log(
                workflow_id,
                stage,
                "SYSTEM",
                "STAGE_COMPLETED",
                {"report_length": len(report)},
            )
            return updates
        except (IncidentTriageError, ValueError) as exc:
            return await self._fail(workflow_id, stage, state, exc)

    async def decision_node(self, state: IncidentTriageState) -> IncidentTriageState:
        """Process human decision injected via resume."""
        workflow_id, stage = _require(state, "workflow_id"), "decision"
        try:
            decision = decision_value(state.get("human_decision"))
            notes = clean_text(state.get("decision_notes"))
            status = "RUNNING" if decision == "REQUEST_MORE_INFO" else decision
            updates = next_state(
                state,
                human_decision=decision,
                decision_notes=notes,
                status=status,
                error=None,
            )
            await self._persist(workflow_id, stage, updates)
            await self._audit.log(
                workflow_id,
                stage,
                "HUMAN",
                "STAGE_COMPLETED",
                {"decision": decision, "notes": notes},
            )
            return updates
        except (IncidentTriageError, ValueError) as exc:
            return await self._fail(workflow_id, stage, state, exc)

    async def _assess_severity(self, state: IncidentTriageState) -> tuple[str, str]:
        """Classify incident severity via scorer or LLM."""
        incident_text = _require(state, "incident_text")
        if self._severity_scorer is not None:
            candidate = self._severity_scorer(incident_text)
            payload = await candidate if asyncio.iscoroutine(candidate) else candidate
            return _severity(payload)
        content = await self._invoke_llm(
            "Classify this incident's severity. Return JSON with keys severity_level "
            "(one of P1, P2, P3, P4) and reasoning (string explaining the classification). "
            f"Incident: {incident_text}"
        )
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise IncidentTriageError(
                f"LLM returned non-JSON severity response: {content[:200]!r}"
            ) from exc
        return _severity(payload)

    async def _generate_report(self, state: IncidentTriageState) -> str:
        """Generate a structured resolution report."""
        incident_text = _require(state, "incident_text")
        severity_level = _require(state, "severity_level")
        reasoning = clean_text(state.get("severity_reasoning")) or "Not available"
        if self._severity_scorer is not None:
            return (
                f"Incident Triage Report\n"
                f"======================\n"
                f"Severity: {severity_level}\n"
                f"Reasoning: {reasoning}\n"
                f"Summary: Incident auto-resolved at {severity_level} severity.\n"
            )
        content = await self._invoke_llm(
            "Generate a brief structured incident resolution report. "
            f"Severity: {severity_level}. Reasoning: {reasoning}. "
            f"Incident: {incident_text}"
        )
        return content or f"Incident resolved at {severity_level} severity."

    async def _invoke_llm(self, prompt: str) -> str:
        """Invoke the LLM synchronously via call_llm wrapper."""
        try:
            from core.llm_client import LLMClientError, call_llm
        except RuntimeError as exc:
            raise IncidentTriageError(str(exc)) from exc
        try:
            return await asyncio.to_thread(call_llm, prompt)
        except (LLMClientError, RuntimeError, TypeError, ValueError) as exc:
            raise IncidentTriageError(f"Incident triage LLM call failed: {exc}") from exc

    async def _persist(self, workflow_id: str, stage: str, state: IncidentTriageState) -> None:
        await self._state.save_checkpoint(
            workflow_id,
            {
                "workflow_type": "incident_triage",
                "stage": stage,
                "status": state.get("status", "RUNNING"),
                "state": dict(state),
            },
        )
        await self._state.update_status(workflow_id, state.get("status", "RUNNING"), stage)

    async def _fail(
        self,
        workflow_id: str,
        stage: str,
        state: IncidentTriageState,
        exc: Exception,
    ) -> IncidentTriageState:
        message = str(exc)
        logger.exception(
            "incident_triage_stage_failed workflow_id=%s stage=%s error_type=%s",
            workflow_id,
            stage,
            type(exc).__name__,
        )
        failed = next_state(state, status="FAILED", error=message)
        await self._persist(workflow_id, stage, failed)
        await self._audit.log(
            workflow_id,
            stage,
            "SYSTEM",
            "STAGE_FAILED",
            {"error": message, "error_type": type(exc).__name__},
        )
        raise IncidentTriageError(message) from exc


def route_after_decision(state: IncidentTriageState) -> str:
    """Route after human decision: resume or loop back."""
    choice = decision_value(state.get("human_decision"))
    if choice == "APPROVED":
        return "resolution_report_node"
    if choice == "REJECTED":
        return "resolution_report_node"
    # REQUEST_MORE_INFO loops back to human_approval
    return "human_approval_node"


def route_after_escalation(state: IncidentTriageState) -> str:
    """Route P1/P2 to human approval, P3/P4 to resolution report.

    Unknown or missing severity is fail-safe: routes to human approval
    so no incident silently bypasses the human gate.
    """
    raw = state.get("severity_level") or ""
    try:
        level = classify_severity(raw)
    except ValueError:
        return "human_approval_node"  # fail-safe: unknown severity → escalate
    return "human_approval_node" if level in ("P1", "P2") else "resolution_report_node"


def _require(state: IncidentTriageState, key: str) -> str:
    try:
        return required_text(state, key)
    except ValueError as exc:
        raise IncidentTriageError(str(exc)) from exc


def _severity(payload: Any) -> tuple[str, str]:
    try:
        from workflows.incident_triage.rules import severity_payload

        return severity_payload(payload)
    except ValueError as exc:
        raise IncidentTriageError(str(exc)) from exc
