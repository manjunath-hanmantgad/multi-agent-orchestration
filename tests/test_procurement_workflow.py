"""Integration tests for procurement LangGraph workflow."""

from __future__ import annotations

from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.audit import AuditLogger
from core.escalation import HumanEscalationManager
from core.schemas import CRMRecordORM
from core.state import StateManager
from workflows.procurement.agents import ProcurementAgents
from workflows.procurement.workflow import ProcurementWorkflow

def _vendor_payload(*, revenue: int = 2500000) -> dict[str, object]:
    """Build realistic mock vendor application payload."""
    return {
        "vendor_name": "Northstar Components LLC",
        "kyc_complete": True,
        "tax_id": "TAX-998877",
        "annual_revenue": revenue,
        "years_in_business": 5,
    }


def _build_workflow(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[ProcurementWorkflow, AuditLogger, async_sessionmaker[AsyncSession]]:
    """Create isolated procurement workflow and DB dependencies."""
    state_manager = StateManager(session_factory=session_factory)
    audit_logger = AuditLogger(session_factory=session_factory)
    escalation = HumanEscalationManager(state_manager=state_manager, audit_logger=audit_logger)
    agents = ProcurementAgents(
        state_manager=state_manager,
        audit_logger=audit_logger,
        escalation_manager=escalation,
        session_factory=session_factory,
        risk_summarizer=lambda _vendor, result: f"Risk score: {result.get('score', 0)}.",
    )
    workflow = ProcurementWorkflow(
        agents=agents,
        state_manager=state_manager,
        checkpointer=MemorySaver(),
    )
    return workflow, audit_logger, session_factory


@pytest.mark.asyncio
async def test_procurement_workflow_approved_path_creates_crm_record(
    in_memory_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Approved decision should create CRM record and complete the workflow."""
    workflow, _audit_logger, session_factory = _build_workflow(in_memory_session_factory)
    workflow_id = str(uuid4())

    paused = await workflow.start({"workflow_id": workflow_id, "vendor_data": _vendor_payload()})
    assert paused.status == "PAUSED"
    snapshot = workflow.build_graph().get_state({"configurable": {"thread_id": workflow_id}})
    assert snapshot.next == ("crm_update_agent",)

    completed = await workflow.resume(workflow_id, decision="APPROVED", notes="Approved by procurement head")
    assert completed.status == "COMPLETED"
    assert completed.crm_record_id is not None
    assert completed.human_decision == "APPROVED"

    async with session_factory() as session:
        row = await session.get(CRMRecordORM, completed.crm_record_id)
    assert row is not None
    assert row.workflow_id == workflow_id
    assert row.decision == "APPROVED"


@pytest.mark.asyncio
async def test_procurement_workflow_rejected_path_skips_crm_and_logs_reason(
    in_memory_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Rejected decision should not create CRM record and must log rejection reason."""
    workflow, audit_logger, session_factory = _build_workflow(in_memory_session_factory)
    workflow_id = str(uuid4())

    await workflow.start({"workflow_id": workflow_id, "vendor_data": _vendor_payload(revenue=500000)})
    rejected = await workflow.resume(workflow_id, decision="REJECTED", notes="Insufficient revenue history")

    assert rejected.status == "REJECTED"
    assert rejected.crm_record_id is None
    assert rejected.human_decision == "REJECTED"

    async with session_factory() as session:
        result = await session.execute(
            select(CRMRecordORM).where(CRMRecordORM.workflow_id == workflow_id)
        )
        rows = result.scalars().all()
    assert rows == []

    trail = await audit_logger.get_trail(workflow_id)
    crm_events = [event for event in trail if event["stage"] == "crm_update_agent"]
    assert crm_events
    assert any(
        event["event_data"].get("rejection_reason") == "Insufficient revenue history"
        for event in crm_events
    )


@pytest.mark.asyncio
async def test_procurement_request_more_info_loops_back_to_due_diligence(
    in_memory_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """REQUEST_MORE_INFO should route back to due diligence and pause again."""
    workflow, _audit_logger, _session_factory = _build_workflow(in_memory_session_factory)
    workflow_id = str(uuid4())

    await workflow.start({"workflow_id": workflow_id, "vendor_data": _vendor_payload()})
    paused_again = await workflow.resume(workflow_id, decision="REQUEST_MORE_INFO", notes="Need updated tax ID")

    assert paused_again.status == "PAUSED"
    assert paused_again.crm_record_id is None
    snapshot = workflow.build_graph().get_state({"configurable": {"thread_id": workflow_id}})
    assert snapshot.next == ("crm_update_agent",)


@pytest.mark.asyncio
async def test_procurement_human_review_audit_payload_excludes_sensitive_text(
    in_memory_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Human-review audit context should not include vendor-identifying values or risk text."""
    workflow, audit_logger, _session_factory = _build_workflow(in_memory_session_factory)
    workflow_id = str(uuid4())
    vendor_data = _vendor_payload()

    await workflow.start({"workflow_id": workflow_id, "vendor_data": vendor_data})
    trail = await audit_logger.get_trail(workflow_id)
    human_review_events = [event for event in trail if event["stage"] == "human_review"]
    assert human_review_events

    for event in human_review_events:
        payload = str(event["event_data"]).lower()
        assert "northstar components llc" not in payload
        assert "tax-998877" not in payload
        assert "risk score:" not in payload
