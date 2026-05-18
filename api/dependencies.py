"""Shared FastAPI dependencies for database and workflow services."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import Depends

from core.audit import AuditLogger
from core.escalation import HumanEscalationManager
from core.registry import WorkflowRegistry, registry
from core.state import StateManager

_state_manager: StateManager | None = None
_audit_logger: AuditLogger | None = None
_escalation_manager: HumanEscalationManager | None = None


def get_registry() -> WorkflowRegistry:
    """Return singleton workflow registry."""
    return registry


async def get_state_manager() -> StateManager:
    """Return workflow state manager instance."""
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager()
    return _state_manager


async def get_audit_logger() -> AuditLogger:
    """Return audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


async def get_escalation_manager(
    state_manager: StateManager = Depends(get_state_manager),
    audit_logger: AuditLogger = Depends(get_audit_logger),
) -> HumanEscalationManager:
    """Return escalation manager instance with shared dependencies."""
    global _escalation_manager
    if _escalation_manager is None:
        _escalation_manager = HumanEscalationManager(
            state_manager=state_manager,
            audit_logger=audit_logger,
        )
    return _escalation_manager


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield async database session from configured core database layer."""
    from core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        yield session
