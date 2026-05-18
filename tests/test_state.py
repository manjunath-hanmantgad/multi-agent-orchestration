"""Tests for checkpoint and run-state persistence manager."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.state import StateError, StateManager


@pytest.mark.asyncio
async def test_save_and_load_checkpoint_upsert(
    in_memory_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """save_checkpoint upserts and load_checkpoint returns merged payload."""
    manager = StateManager(session_factory=in_memory_session_factory)
    workflow_id = str(uuid4())

    await manager.save_checkpoint(workflow_id, {"workflow_type": "compliance_review", "stage": "intake"})
    await manager.save_checkpoint(workflow_id, {"stage": "rule_check", "risk_score": 42})

    checkpoint = await manager.load_checkpoint(workflow_id)
    assert checkpoint is not None
    assert checkpoint["workflow_type"] == "compliance_review"
    assert checkpoint["stage"] == "rule_check"
    assert checkpoint["risk_score"] == 42


@pytest.mark.asyncio
async def test_update_status_and_get_run(
    in_memory_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """update_status writes state and get_run returns WorkflowRun model."""
    manager = StateManager(session_factory=in_memory_session_factory)
    workflow_id = str(uuid4())

    await manager.save_checkpoint(workflow_id, {"workflow_type": "compliance_review", "stage": "intake"})
    await manager.update_status(workflow_id, "PAUSED", "human_review")

    run = await manager.get_run(workflow_id)
    assert run is not None
    assert run.status.value == "PAUSED"
    assert run.current_stage == "human_review"


@pytest.mark.asyncio
async def test_update_status_unknown_workflow_raises(
    in_memory_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """update_status should fail when workflow run does not exist."""
    manager = StateManager(session_factory=in_memory_session_factory)

    with pytest.raises(StateError, match="Workflow run not found"):
        await manager.update_status(str(uuid4()), "PAUSED", "human_review")


@pytest.mark.asyncio
async def test_load_checkpoint_missing_and_invalid_id(
    in_memory_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Edge and failure paths for load_checkpoint and workflow id validation."""
    manager = StateManager(session_factory=in_memory_session_factory)

    assert await manager.load_checkpoint(str(uuid4())) is None

    with pytest.raises(StateError, match="workflow_id must be a valid UUID"):
        await manager.save_checkpoint("not-a-uuid", {"stage": "intake"})
