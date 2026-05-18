"""Tests for human escalation pause/resume lifecycle."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.audit import AuditLogger
from core.escalation import EscalationError, HumanEscalationManager
from core.state import StateManager


def _build_manager(
    factory: async_sessionmaker[AsyncSession],
) -> HumanEscalationManager:
    """Build escalation manager wired to the shared in-memory session factory."""
    state_manager = StateManager(session_factory=factory)
    audit_logger = AuditLogger(session_factory=factory)
    return HumanEscalationManager(state_manager=state_manager, audit_logger=audit_logger)


@pytest.mark.asyncio
async def test_request_review_adds_pending_item(
    in_memory_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """request_review pauses run and exposes it in pending review list."""
    manager = _build_manager(in_memory_session_factory)
    workflow_id = str(uuid4())

    await manager.request_review(workflow_id, {"doc_id": "DOC-1", "risk": "medium"})

    pending = await manager.get_pending_reviews()
    assert len(pending) == 1
    assert pending[0]["workflow_id"] == workflow_id
    assert pending[0]["status"] == "PAUSED"
    assert pending[0]["review_context"]["doc_id"] == "DOC-1"


@pytest.mark.asyncio
async def test_submit_decision_request_more_info_sets_running_and_logs(
    in_memory_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """REQUEST_MORE_INFO transitions back to RUNNING and emits audit entries."""
    manager = _build_manager(in_memory_session_factory)
    workflow_id = str(uuid4())

    await manager.request_review(workflow_id, {"doc_id": "DOC-2"})
    result = await manager.submit_decision(
        workflow_id,
        actor="HUMAN",
        decision="REQUEST_MORE_INFO",
        notes="Need revised declaration",
    )

    assert result["status"] == "RUNNING"
    assert result["decision"] == "REQUEST_MORE_INFO"

    state_manager = StateManager(session_factory=in_memory_session_factory)
    run = await state_manager.get_run(workflow_id)
    assert run is not None
    assert run.status.value == "RUNNING"

    audit_logger = AuditLogger(session_factory=in_memory_session_factory)
    trail = await audit_logger.get_trail(workflow_id)
    event_types = [event["event_type"] for event in trail]
    assert "REVIEW_REQUESTED" in event_types
    assert "DECISION_SUBMITTED" in event_types


@pytest.mark.asyncio
async def test_submit_decision_invalid_value_raises(
    in_memory_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Invalid decision values are rejected before state mutation."""
    manager = _build_manager(in_memory_session_factory)
    workflow_id = str(uuid4())

    await manager.request_review(workflow_id, {"doc_id": "DOC-3"})

    with pytest.raises(EscalationError, match="Invalid decision"):
        await manager.submit_decision(
            workflow_id,
            actor="HUMAN",
            decision="MAYBE",
            notes="undecided",
        )
