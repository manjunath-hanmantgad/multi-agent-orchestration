"""Lightweight route tests for the demo UI pages."""

from __future__ import annotations

import importlib
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.audit import AuditLogger
from core.escalation import HumanEscalationManager
from core.registry import WorkflowRegistry
from core.state import StateManager
from workflows.procurement.agents import ProcurementAgents
from workflows.procurement.workflow import ProcurementWorkflow


def _vendor_data() -> dict:
    return {
        "vendor_name": "Summit Industrial Co",
        "kyc_complete": True,
        "tax_id": "TAX-12345",
        "annual_revenue": 3000000,
        "years_in_business": 6,
    }


def _build_procurement_stack(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[WorkflowRegistry, StateManager, AuditLogger, HumanEscalationManager]:
    state_manager = StateManager(session_factory=session_factory)
    audit_logger = AuditLogger(session_factory=session_factory)
    escalation_manager = HumanEscalationManager(
        state_manager=state_manager,
        audit_logger=audit_logger,
    )
    agents = ProcurementAgents(
        state_manager=state_manager,
        audit_logger=audit_logger,
        escalation_manager=escalation_manager,
        session_factory=session_factory,
        risk_summarizer=lambda _vendor, result: f"Risk score: {result.get('score', 0)}.",
    )
    workflow = ProcurementWorkflow(agents=agents, state_manager=state_manager)
    registry = WorkflowRegistry(auto_discover=False)
    registry.register(workflow)
    return registry, state_manager, audit_logger, escalation_manager


@pytest.fixture
def ui_client(
    in_memory_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    """Build isolated UI test client backed by in-memory SQLite and mocked LLM path."""
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    app_module = importlib.import_module("app.main")
    deps = importlib.import_module("api.dependencies")
    registry, state_manager, audit_logger, escalation_manager = _build_procurement_stack(
        in_memory_session_factory
    )

    deps._state_manager = None
    deps._audit_logger = None
    deps._escalation_manager = None
    monkeypatch.setattr(app_module, "registry", registry)
    monkeypatch.setattr(app_module, "AsyncSessionLocal", in_memory_session_factory)
    monkeypatch.setattr(app_module, "audit_logger", audit_logger)

    async def _override_get_db_session():
        async with in_memory_session_factory() as session:
            yield session

    async def _override_state_manager() -> StateManager:
        return state_manager

    async def _override_audit_logger() -> AuditLogger:
        return audit_logger

    async def _override_escalation() -> HumanEscalationManager:
        return escalation_manager

    app_module.app.dependency_overrides[deps.get_registry] = lambda: registry
    app_module.app.dependency_overrides[deps.get_state_manager] = _override_state_manager
    app_module.app.dependency_overrides[deps.get_audit_logger] = _override_audit_logger
    app_module.app.dependency_overrides[deps.get_escalation_manager] = _override_escalation
    app_module.app.dependency_overrides[deps.get_db_session] = _override_get_db_session

    with TestClient(app_module.app) as client:
        yield client

    app_module.app.dependency_overrides.clear()


def test_dashboard_renders_with_empty_database(ui_client: TestClient) -> None:
    """Dashboard route returns 200 even when no workflow runs exist."""
    response = ui_client.get("/dashboard")
    assert response.status_code == 200
    assert "Dashboard" in response.text or "workflow" in response.text.lower()


def test_root_redirects_to_dashboard(ui_client: TestClient) -> None:
    """Root path redirects to /dashboard."""
    response = ui_client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert "/dashboard" in response.headers.get("location", "")


def test_review_unknown_workflow_returns_404(ui_client: TestClient) -> None:
    """Review page returns 404 for an unknown workflow id."""
    response = ui_client.get(f"/review/{uuid4()}")
    assert response.status_code == 404


def test_audit_unknown_workflow_returns_404(ui_client: TestClient) -> None:
    """Audit page returns 404 for an unknown workflow id."""
    response = ui_client.get(f"/audit/{uuid4()}")
    assert response.status_code == 404


def _start_procurement(client: TestClient) -> str:
    """Start a procurement workflow and return its workflow_id."""
    response = client.post(
        "/api/workflows/start",
        json={"workflow_type": "procurement", "input_data": {"vendor_data": _vendor_data()}},
    )
    assert response.status_code == 200
    return response.json()["data"]["workflow_id"]


def test_review_paused_workflow_renders_decision_form(ui_client: TestClient) -> None:
    """Review page renders 200 with decision form for a paused workflow."""
    workflow_id = _start_procurement(ui_client)
    response = ui_client.get(f"/review/{workflow_id}")
    assert response.status_code == 200
    assert "Approve" in response.text or "approve" in response.text.lower()


def test_audit_page_renders_event_timeline(ui_client: TestClient) -> None:
    """Audit page returns 200 and shows workflow context for a known workflow."""
    workflow_id = _start_procurement(ui_client)
    response = ui_client.get(f"/audit/{workflow_id}")
    assert response.status_code == 200
    assert "audit" in response.text.lower() or workflow_id[:8] in response.text


def test_decision_submit_flow_approves_and_completes(ui_client: TestClient) -> None:
    """Decision submitted via API endpoint completes the paused workflow."""
    workflow_id = _start_procurement(ui_client)

    decide = ui_client.post(
        f"/api/workflows/{workflow_id}/decide",
        json={"actor": "HUMAN", "decision": "APPROVED", "notes": "approved via UI test"},
    )
    assert decide.status_code == 200
    assert decide.json()["success"] is True
    assert decide.json()["data"]["result"]["status"] == "COMPLETED"
    assert decide.json()["data"]["result"]["crm_record_id"] is not None
