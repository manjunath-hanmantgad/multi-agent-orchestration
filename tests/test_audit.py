"""Tests for immutable audit trail logging behavior."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.audit import AuditError, AuditLogger
from core.schemas import WorkflowRunORM


async def _seed_workflow(factory: async_sessionmaker[AsyncSession], workflow_id: str) -> None:
    """Insert a workflow row required for audit foreign-key validation."""
    async with factory() as session:
        session.add(
            WorkflowRunORM(
                id=workflow_id,
                workflow_type="compliance_review",
                status="RUNNING",
                current_stage="intake",
                payload={},
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_log_appends_and_get_trail_orders_events(
    in_memory_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Audit logging appends entries and returns chronological trail."""
    workflow_id = str(uuid4())
    await _seed_workflow(in_memory_session_factory, workflow_id)

    logger = AuditLogger(session_factory=in_memory_session_factory)

    await logger.log(workflow_id, "intake", "SYSTEM", "INGESTED", {"step": 1})
    await logger.log(workflow_id, "rule_check", "HUMAN", "REVIEWED", {"step": 2})

    trail = await logger.get_trail(workflow_id)
    assert len(trail) == 2
    assert trail[0]["event_type"] == "INGESTED"
    assert trail[1]["event_type"] == "REVIEWED"


@pytest.mark.asyncio
async def test_log_with_invalid_workflow_id_raises(
    in_memory_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Unknown workflow ids are rejected with AuditError."""
    logger = AuditLogger(session_factory=in_memory_session_factory)

    with pytest.raises(AuditError, match="Invalid workflow_id"):
        await logger.log(str(uuid4()), "intake", "SYSTEM", "INGESTED", {"step": 1})


@pytest.mark.asyncio
async def test_log_rejects_invalid_actor_and_empty_trail(
    in_memory_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Invalid actors fail validation and empty trails return no rows."""
    workflow_id = str(uuid4())
    await _seed_workflow(in_memory_session_factory, workflow_id)

    logger = AuditLogger(session_factory=in_memory_session_factory)

    with pytest.raises(AuditError, match="actor must be one of"):
        await logger.log(workflow_id, "intake", "BOT", "INGESTED", {"step": 1})

    trail = await logger.get_trail(workflow_id)
    assert trail == []


@pytest.mark.asyncio
async def test_log_handles_concurrent_calls_safely(
    in_memory_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Concurrent log calls append all events without dropping entries."""
    workflow_id = str(uuid4())
    await _seed_workflow(in_memory_session_factory, workflow_id)
    logger = AuditLogger(session_factory=in_memory_session_factory)

    await asyncio.gather(
        *[
            logger.log(
                workflow_id,
                "risk_scoring",
                "SYSTEM",
                "SCORING_COMPLETED",
                {"index": index},
            )
            for index in range(20)
        ]
    )

    trail = await logger.get_trail(workflow_id)
    assert len(trail) == 20
    indices = sorted(event["event_data"]["index"] for event in trail)
    assert indices == list(range(20))
