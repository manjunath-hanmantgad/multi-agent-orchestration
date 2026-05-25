"""Integration tests for incident triage LangGraph workflow."""

from __future__ import annotations

from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.audit import AuditLogger
from core.escalation import HumanEscalationManager
from core.state import StateManager
from workflows.incident_triage.agents import IncidentTriageAgents, route_after_escalation
from workflows.incident_triage.rules import classify_severity
from workflows.incident_triage.workflow import IncidentTriageWorkflow


def _build_workflow(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    severity_level: str,
) -> tuple[IncidentTriageWorkflow, AuditLogger, str]:
    """Construct workflow module wired to isolated DB with deterministic scorer."""
    workflow_id = str(uuid4())
    state_manager = StateManager(session_factory=session_factory)
    audit_logger = AuditLogger(session_factory=session_factory)
    escalation = HumanEscalationManager(state_manager=state_manager, audit_logger=audit_logger)

    def _scorer(incident_text: str) -> dict[str, object]:
        return {
            "severity_level": severity_level,
            "reasoning": f"Deterministic severity for test: {severity_level}",
        }

    agents = IncidentTriageAgents(
        state_manager=state_manager,
        audit_logger=audit_logger,
        escalation_manager=escalation,
        severity_scorer=_scorer,
    )
    workflow = IncidentTriageWorkflow(
        agents=agents,
        state_manager=state_manager,
        checkpointer=MemorySaver(),
    )
    return workflow, audit_logger, workflow_id


@pytest.mark.asyncio
async def test_p1_workflow_reaches_paused(
    in_memory_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """P1 severity incident pauses at human approval."""
    workflow, audit_logger, workflow_id = _build_workflow(
        in_memory_session_factory,
        severity_level="P1",
    )

    result = await workflow.start(
        {
            "workflow_id": workflow_id,
            "incident_text": "Production database connection pool exhausted, affecting 3 services.",
        }
    )
    assert result.status == "PAUSED"
    assert result.severity_level == "P1"
    assert result.severity_reasoning is not None
    assert "Deterministic severity" in result.severity_reasoning

    snapshot = workflow.build_graph().get_state({"configurable": {"thread_id": workflow_id}})
    assert snapshot.next == ("decision_node",)

    trial = await audit_logger.get_trail(workflow_id)
    stages = {event["stage"] for event in trial}
    assert "intake" in stages
    assert "severity_assessment" in stages
    assert "escalation_decision" in stages
    assert "human_approval" in stages


@pytest.mark.asyncio
async def test_p4_workflow_completes_without_human_approval(
    in_memory_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """P4 severity incident auto-resolves without human approval."""
    workflow, audit_logger, workflow_id = _build_workflow(
        in_memory_session_factory,
        severity_level="P4",
    )

    result = await workflow.start(
        {
            "workflow_id": workflow_id,
            "incident_text": "Minor UI glitch on settings page, no users affected.",
        }
    )
    assert result.status == "COMPLETED"
    assert result.severity_level == "P4"
    assert result.severity_reasoning is not None
    assert result.resolution_report is not None
    assert len(result.resolution_report) > 0

    trial = await audit_logger.get_trail(workflow_id)
    stages = {event["stage"] for event in trial}
    assert "intake" in stages
    assert "severity_assessment" in stages
    assert "escalation_decision" in stages
    assert "human_approval" not in stages
    assert "resolution_report" in stages


@pytest.mark.asyncio
async def test_severity_assessment_returns_valid_level(
    in_memory_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """severity_assessment node returns valid severity level."""
    workflow, audit_logger, workflow_id = _build_workflow(
        in_memory_session_factory,
        severity_level="P2",
    )

    result = await workflow.start(
        {
            "workflow_id": workflow_id,
            "incident_text": "Suspicious login attempts detected from multiple IPs.",
        }
    )
    assert result.severity_level in ("P1", "P2", "P3", "P4")
    assert result.severity_reasoning is not None


@pytest.mark.asyncio
async def test_resolution_report_generates_non_empty_text(
    in_memory_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """resolution_report node generates non-empty report text for low severity."""
    workflow, audit_logger, workflow_id = _build_workflow(
        in_memory_session_factory,
        severity_level="P3",
    )

    result = await workflow.start(
        {
            "workflow_id": workflow_id,
            "incident_text": "Non-critical log alert from monitoring system.",
        }
    )
    assert result.status == "COMPLETED"
    assert result.resolution_report is not None
    assert len(result.resolution_report) > 0
    assert "P3" in result.resolution_report or "Severity" in result.resolution_report


class TestUnknownSeverity:
    """Tests for fail-safe behavior on unrecognised severity labels."""

    def test_classify_severity_raises_on_unknown_label(self):
        """classify_severity must raise ValueError for unknown labels,
        not silently default to P3 (which would auto-resolve)."""
        with pytest.raises(ValueError, match="alien_severity"):
            classify_severity("alien_severity")

    def test_route_after_escalation_failsafe_routes_unknown_to_human(self):
        """route_after_escalation must route unknown severity labels
        to human_approval_node, not silently auto-resolve."""
        state = {"severity_level": "alien_severity"}
        next_node = route_after_escalation(state)
        assert next_node == "human_approval_node"

    def test_route_after_escalation_missing_severity_routes_to_human(self):
        """Missing severity_level from state must also route to
        human_approval_node as a fail-safe."""
        state: dict = {}
        next_node = route_after_escalation(state)
        assert next_node == "human_approval_node"
