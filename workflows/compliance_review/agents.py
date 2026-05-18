"""Agent nodes for compliance workflow execution."""
from __future__ import annotations
import asyncio
import json
import logging
from typing import Any, Callable

from core.audit import AuditLogger
from core.escalation import HumanEscalationManager
from core.services.document_parser import DocumentParser, DocumentParserError
from core.services.report_generator import ReportGenerationError, ReportGenerator
from core.services.rule_engine import RuleEngine, RuleEngineError
from core.state import StateManager
from workflows.compliance_review.schema import (
    ComplianceReviewState,
    build_extracted_data,
    clean_text,
    decision_value,
    next_state,
    required_results,
    required_text,
    risk_payload,
    rule_payload,
    validate_rules,
)
logger = logging.getLogger(__name__)
class ComplianceWorkflowError(RuntimeError):
    """Raised when workflow stage execution fails."""

class ComplianceReviewAgents:
    """Node handlers with persistence and audit side effects."""

    def __init__(
        self,
        *,
        state_manager: StateManager | None = None,
        audit_logger: AuditLogger | None = None,
        escalation_manager: HumanEscalationManager | None = None,
        document_parser: DocumentParser | None = None,
        rule_engine: RuleEngine | None = None,
        report_generator: ReportGenerator | None = None,
        risk_scorer: Callable[[dict[str, list[dict[str, Any]]]], Any] | None = None,
    ) -> None:
        self._state = state_manager or StateManager()
        self._audit = audit_logger or AuditLogger()
        self._escalation = escalation_manager or HumanEscalationManager(
            state_manager=self._state,
            audit_logger=self._audit,
        )
        self._parser = document_parser or DocumentParser()
        self._rules = rule_engine or RuleEngine()
        self._reports = report_generator or ReportGenerator()
        self._risk_scorer = risk_scorer

    async def intake_agent(self, state: ComplianceReviewState) -> ComplianceReviewState:
        workflow_id, stage = _require(state, "workflow_id"), "intake_agent"
        try:
            parsed = self._parser.parse(_require(state, "document_path"))
            extracted = build_extracted_data(parsed, state.get("input_fields"))
            updates = next_state(state, extracted_data=extracted, status="RUNNING", error=None)
            await self._persist(workflow_id, stage, updates)
            fields = extracted.get("structured_fields", {})
            await self._audit.log(
                workflow_id,
                stage,
                "SYSTEM",
                "STAGE_COMPLETED",
                {
                    "metadata": extracted.get("metadata", {}),
                    "structured_field_count": len(fields) if isinstance(fields, dict) else 0,
                },
            )
            return updates
        except (DocumentParserError, RuleEngineError, ComplianceWorkflowError, ValueError) as exc:
            return await self._fail(workflow_id, stage, state, exc)

    async def rule_check_agent(self, state: ComplianceReviewState) -> ComplianceReviewState:
        workflow_id, stage = _require(state, "workflow_id"), "rule_check_agent"
        try:
            rules = load_and_validate_rules(self._rules)
            results = self._rules.evaluate(rule_payload(state), rules)
            updates = next_state(state, rule_results=results, status="RUNNING", error=None)
            await self._persist(workflow_id, stage, updates)
            await self._audit.log(
                workflow_id,
                stage,
                "SYSTEM",
                "STAGE_COMPLETED",
                {key: len(results.get(key, [])) for key in ("passed", "failed", "flagged")},
            )
            return updates
        except (RuleEngineError, ComplianceWorkflowError, ValueError) as exc:
            return await self._fail(workflow_id, stage, state, exc)

    async def risk_scoring_agent(self, state: ComplianceReviewState) -> ComplianceReviewState:
        workflow_id, stage = _require(state, "workflow_id"), "risk_scoring_agent"
        try:
            score, reasoning = await self._score(required_results(state))
            updates = next_state(
                state,
                risk_score=score,
                risk_reasoning=reasoning,
                status="RUNNING",
                error=None,
            )
            await self._persist(workflow_id, stage, updates)
            await self._audit.log(
                workflow_id,
                stage,
                "SYSTEM",
                "STAGE_COMPLETED",
                {"risk_score": score, "risk_reasoning": reasoning},
            )
            return updates
        except (ComplianceWorkflowError, ValueError) as exc:
            return await self._fail(workflow_id, stage, state, exc)

    async def human_review_node(self, state: ComplianceReviewState) -> ComplianceReviewState:
        workflow_id, stage = _require(state, "workflow_id"), "human_review_node"
        try:
            extracted_data = state.get("extracted_data", {})
            metadata = extracted_data.get("metadata", {}) if isinstance(extracted_data, dict) else {}
            fields = extracted_data.get("structured_fields", {}) if isinstance(extracted_data, dict) else {}
            results = state.get("rule_results", {})
            context = {
                "document_type": metadata.get("file_type"),
                "page_count": metadata.get("page_count"),
                "field_keys": sorted(key for key in fields.keys() if key != "full_text")
                if isinstance(fields, dict)
                else [],
                "risk_score": state.get("risk_score"),
                "rule_results_summary": {
                    key: len(results.get(key, [])) for key in ("passed", "failed", "flagged")
                }
                if isinstance(results, dict)
                else {"passed": 0, "failed": 0, "flagged": 0},
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
        except (ComplianceWorkflowError, ValueError) as exc:
            return await self._fail(workflow_id, stage, state, exc)

    async def decision_agent(self, state: ComplianceReviewState) -> ComplianceReviewState:
        workflow_id, stage = _require(state, "workflow_id"), "decision_agent"
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
        except (ComplianceWorkflowError, ValueError) as exc:
            return await self._fail(workflow_id, stage, state, exc)

    async def certificate_agent(self, state: ComplianceReviewState) -> ComplianceReviewState:
        return await self._finalize("certificate_agent", state, approved=True)

    async def rejection_agent(self, state: ComplianceReviewState) -> ComplianceReviewState:
        return await self._finalize("rejection_agent", state, approved=False)

    async def _finalize(
        self,
        stage: str,
        state: ComplianceReviewState,
        *,
        approved: bool,
    ) -> ComplianceReviewState:
        workflow_id = _require(state, "workflow_id")
        try:
            path = await self._report(workflow_id, state, approved)
            updates = next_state(state, report_path=path, status="COMPLETED", error=None)
            await self._persist(workflow_id, stage, updates)
            await self._audit.log(
                workflow_id,
                stage,
                "SYSTEM",
                "STAGE_COMPLETED",
                {"report_path": path, "outcome": "APPROVED" if approved else "REJECTED"},
            )
            return updates
        except (ReportGenerationError, ComplianceWorkflowError, ValueError) as exc:
            return await self._fail(workflow_id, stage, state, exc)

    async def _persist(self, workflow_id: str, stage: str, state: ComplianceReviewState) -> None:
        await self._state.save_checkpoint(
            workflow_id,
            {
                "workflow_type": "compliance_review",
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
        state: ComplianceReviewState,
        exc: Exception,
    ) -> ComplianceReviewState:
        message = str(exc)
        logger.exception(
            "compliance_stage_failed workflow_id=%s stage=%s error_type=%s",
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
        raise ComplianceWorkflowError(message) from exc

    async def _score(self, results: dict[str, list[dict[str, Any]]]) -> tuple[int, str]:
        if self._risk_scorer is not None:
            candidate = self._risk_scorer(results)
            payload = await candidate if asyncio.iscoroutine(candidate) else candidate
            return _risk(payload)
        content = await self._invoke_llm(
            "Return JSON with keys risk_score (0-100 int) and risk_reasoning. "
            f"Rule results: {json.dumps(results, ensure_ascii=True)}"
        )
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            payload = {"risk_score": 50, "risk_reasoning": content.strip() or "No output"}
        return _risk(payload)

    async def _invoke_llm(self, prompt: str) -> str:
        try:
            from core.llm_client import LLMClientError, get_llm_client
        except RuntimeError as exc:
            raise ComplianceWorkflowError(str(exc)) from exc
        try:
            response = await asyncio.to_thread(get_llm_client().invoke, prompt)
            return str(getattr(response, "content", response))
        except (LLMClientError, RuntimeError, TypeError, ValueError) as exc:
            raise ComplianceWorkflowError(f"Risk scoring LLM call failed: {exc}") from exc

    async def _report(self, workflow_id: str, state: ComplianceReviewState, approved: bool) -> str:
        run = await self._state.get_run(workflow_id)
        if run is None:
            raise ComplianceWorkflowError(f"Workflow run not found: {workflow_id}")
        trail = await self._audit.get_trail(workflow_id)
        if approved:
            return self._reports.generate_compliance_report(run, trail)
        reason = clean_text(state.get("decision_notes")) or "Rejected during human review"
        return self._reports.generate_rejection_report(run, reason, trail)

def load_and_validate_rules(rule_engine: RuleEngine) -> list[dict[str, Any]]:
    return validate_rules(rule_engine.load_rules("compliance_review"))

def route_after_decision(state: ComplianceReviewState) -> str:
    choice = decision_value(state.get("human_decision"))
    if choice == "APPROVED":
        return "certificate_agent"
    if choice == "REJECTED":
        return "rejection_agent"
    return "rule_check_agent"

def _require(state: ComplianceReviewState, key: str) -> str:
    try:
        return required_text(state, key)
    except ValueError as exc:
        raise ComplianceWorkflowError(str(exc)) from exc

def _risk(payload: Any) -> tuple[int, str]:
    try:
        return risk_payload(payload)
    except ValueError as exc:
        raise ComplianceWorkflowError(str(exc)) from exc
