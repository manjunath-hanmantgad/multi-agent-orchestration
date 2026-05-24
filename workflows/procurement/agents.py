"""Agent nodes for procurement workflow execution."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.audit import AuditLogger
from core.escalation import HumanEscalationManager
from core.schemas import CRMRecordORM
from core.state import StateManager
from workflows.procurement.schema import (
    ProcurementState,
    clean_text,
    decision_value,
    next_state,
    required_text,
)

logger = logging.getLogger(__name__)


class ProcurementWorkflowError(RuntimeError):
    """Raised when procurement stage execution fails."""


class ProcurementAgents:
    """Node handlers with persistence, audit logging, and CRM updates."""

    def __init__(
        self,
        *,
        state_manager: StateManager | None = None,
        audit_logger: AuditLogger | None = None,
        escalation_manager: HumanEscalationManager | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        risk_summarizer: Callable[[dict[str, Any], dict[str, Any]], Any] | None = None,
    ) -> None:
        self._state = state_manager or StateManager()
        self._audit = audit_logger or AuditLogger()
        self._escalation = escalation_manager or HumanEscalationManager(
            state_manager=self._state,
            audit_logger=self._audit,
        )
        self._session_factory = session_factory or _default_session_factory()
        self._risk_summarizer = risk_summarizer

    async def intake_agent(self, state: ProcurementState) -> ProcurementState:
        workflow_id, stage = _require(state, "workflow_id"), "intake_agent"
        try:
            vendor_data = state.get("vendor_data")
            if not isinstance(vendor_data, dict):
                raise ProcurementWorkflowError("vendor_data must be a dictionary")
            updates = next_state(state, vendor_data=dict(vendor_data), status="RUNNING", error=None)
            await self._persist(workflow_id, stage, updates)
            await self._audit.log(
                workflow_id,
                stage,
                "SYSTEM",
                "STAGE_COMPLETED",
                {"vendor_fields": sorted(vendor_data.keys())},
            )
            return updates
        except (ProcurementWorkflowError, ValueError) as exc:
            return await self._fail(workflow_id, stage, state, exc)

    async def due_diligence_agent(self, state: ProcurementState) -> ProcurementState:
        workflow_id, stage = _require(state, "workflow_id"), "due_diligence_agent"
        try:
            vendor_data = state.get("vendor_data")
            if not isinstance(vendor_data, dict):
                raise ProcurementWorkflowError("vendor_data must be a dictionary")
            result = _evaluate_vendor(vendor_data)
            summary = await self._risk_summary(vendor_data, result)
            updates = next_state(
                state,
                due_diligence_result=result,
                risk_summary=summary,
                status="RUNNING",
                error=None,
            )
            await self._persist(workflow_id, stage, updates)
            await self._audit.log(
                workflow_id,
                stage,
                "SYSTEM",
                "STAGE_COMPLETED",
                {"pass_count": len(result["passed"]), "fail_count": len(result["failed"])},
            )
            return updates
        except (ProcurementWorkflowError, ValueError) as exc:
            return await self._fail(workflow_id, stage, state, exc)

    async def human_review_node(self, state: ProcurementState) -> ProcurementState:
        workflow_id, stage = _require(state, "workflow_id"), "human_review_node"
        try:
            result = state.get("due_diligence_result", {})
            vendor_data = state.get("vendor_data", {})
            context = {
                "vendor_field_keys": sorted(vendor_data.keys()) if isinstance(vendor_data, dict) else [],
                "due_diligence_score": result.get("score") if isinstance(result, dict) else None,
                "due_diligence_summary": {
                    "passed": len(result.get("passed", [])) if isinstance(result, dict) else 0,
                    "failed": len(result.get("failed", [])) if isinstance(result, dict) else 0,
                },
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
        except (ProcurementWorkflowError, ValueError) as exc:
            return await self._fail(workflow_id, stage, state, exc)

    async def crm_update_agent(self, state: ProcurementState) -> ProcurementState:
        workflow_id, stage = _require(state, "workflow_id"), "crm_update_agent"
        try:
            decision = decision_value(state.get("human_decision"))
            notes = clean_text(state.get("decision_notes"))
            if decision == "APPROVED":
                record_id = await self._create_crm_record(workflow_id, state, decision, notes)
                updates = next_state(
                    state,
                    crm_record_id=record_id,
                    human_decision=decision,
                    status="COMPLETED",
                    error=None,
                )
                event_data = {"decision": decision, "crm_record_id": record_id}
            elif decision == "REJECTED":
                updates = next_state(state, human_decision=decision, status="REJECTED", error=None)
                event_data = {"decision": decision, "rejection_reason": notes}
            else:
                updates = next_state(state, human_decision=decision, status="RUNNING", error=None)
                event_data = {"decision": decision, "notes": notes}
            await self._persist(workflow_id, stage, updates)
            await self._audit.log(workflow_id, stage, "HUMAN", "STAGE_COMPLETED", event_data)
            return updates
        except (ProcurementWorkflowError, ValueError) as exc:
            return await self._fail(workflow_id, stage, state, exc)

    async def _create_crm_record(
        self,
        workflow_id: str,
        state: ProcurementState,
        decision: str,
        notes: str,
    ) -> str:
        vendor_data = state.get("vendor_data")
        if not isinstance(vendor_data, dict):
            raise ProcurementWorkflowError("vendor_data must be a dictionary")
        record_id = str(uuid4())
        vendor_name = clean_text(vendor_data.get("vendor_name")) or "Unknown Vendor"
        async with self._session_factory() as session:
            session.add(
                CRMRecordORM(
                    id=record_id,
                    workflow_id=workflow_id,
                    vendor_name=vendor_name,
                    decision=decision,
                    decision_by="HUMAN",
                    decided_at=datetime.now(timezone.utc),
                    notes=notes,
                )
            )
            await session.commit()
        return record_id

    async def _persist(self, workflow_id: str, stage: str, state: ProcurementState) -> None:
        await self._state.save_checkpoint(
            workflow_id,
            {
                "workflow_type": "procurement",
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
        state: ProcurementState,
        exc: Exception,
    ) -> ProcurementState:
        message = str(exc)
        logger.exception(
            "procurement_stage_failed workflow_id=%s stage=%s error_type=%s",
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
        raise ProcurementWorkflowError(message) from exc

    async def _risk_summary(
        self,
        vendor_data: dict[str, Any],
        result: dict[str, Any],
    ) -> str:
        if self._risk_summarizer is not None:
            payload = self._risk_summarizer(vendor_data, result)
            value = await payload if asyncio.iscoroutine(payload) else payload
            return clean_text(value) or "No risk summary provided."
        import sys as _sys
        print(f"DEBUG _risk_summary: id(type(self))={id(type(self))}, _invoke_llm={type(self).__dict__.get('_invoke_llm', 'NOT_IN_DICT')!r}", file=_sys.stderr)
        return await self._invoke_llm(vendor_data, result)

    async def _invoke_llm(self, vendor_data: dict[str, Any], result: dict[str, Any]) -> str:
        prompt = (
            "Summarize procurement due diligence risk in one short paragraph. "
            f"Vendor data: {json.dumps(vendor_data, ensure_ascii=True)} "
            f"Checks: {json.dumps(result, ensure_ascii=True)}"
        )
        try:
            from core.llm_client import LLMClientError, call_llm
        except RuntimeError as exc:
            raise ProcurementWorkflowError(str(exc)) from exc
        try:
            content = clean_text(await asyncio.to_thread(call_llm, prompt))
            return content or "No risk summary provided."
        except (LLMClientError, RuntimeError, TypeError, ValueError) as exc:
            raise ProcurementWorkflowError(f"Due diligence LLM call failed: {exc}") from exc


def route_after_crm_update(state: ProcurementState) -> str:
    """Route REQUEST_MORE_INFO to due diligence loop, else finish."""
    decision = decision_value(state.get("human_decision"))
    return "due_diligence_agent" if decision == "REQUEST_MORE_INFO" else "end"


def _require(state: ProcurementState, key: str) -> str:
    try:
        return required_text(state, key)
    except ValueError as exc:
        raise ProcurementWorkflowError(str(exc)) from exc


def _evaluate_vendor(vendor_data: dict[str, Any]) -> dict[str, list[str] | int]:
    checks = {
        "kyc_complete": bool(vendor_data.get("kyc_complete")),
        "tax_id_present": bool(clean_text(vendor_data.get("tax_id"))),
        "annual_revenue_minimum": float(vendor_data.get("annual_revenue", 0)) >= 1000000,
        "years_in_business_minimum": int(vendor_data.get("years_in_business", 0)) >= 2,
    }
    passed = sorted(key for key, ok in checks.items() if ok)
    failed = sorted(key for key, ok in checks.items() if not ok)
    score = int((len(passed) / max(len(checks), 1)) * 100)
    return {"passed": passed, "failed": failed, "score": score}


def _default_session_factory() -> async_sessionmaker[AsyncSession]:
    """Resolve default DB session factory lazily from core.database."""
    try:
        from core.database import AsyncSessionLocal
    except RuntimeError as exc:
        raise ProcurementWorkflowError("Missing DATABASE_URL for procurement CRM updates") from exc
    return AsyncSessionLocal
