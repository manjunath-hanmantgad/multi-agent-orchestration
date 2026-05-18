"""Tests for FastAPI workflow, approval, and audit endpoints."""

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


def _vendor_data() -> dict[str, object]:
    return {
        "vendor_name": "Summit Industrial Co",
        "kyc_complete": True,
        "tax_id": "TAX-12345",
        "annual_revenue": 3000000,
        "years_in_business": 6,
    }


def _build_procurement_registry(
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
def api_client(
    in_memory_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    """Build isolated API test client backed by in-memory SQLite and mocked LLM path."""
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    api_main = importlib.import_module("api.main")
    deps = importlib.import_module("api.dependencies")
    registry, state_manager, audit_logger, escalation_manager = _build_procurement_registry(
        in_memory_session_factory
    )

    monkeypatch.setattr(api_main, "get_registry", lambda: registry)
    deps._state_manager = None
    deps._audit_logger = None
    deps._escalation_manager = None

    app = api_main.create_app()

    async def _override_get_db_session():
        async with in_memory_session_factory() as session:
            yield session

    async def _override_state_manager() -> StateManager:
        return state_manager

    async def _override_audit_logger() -> AuditLogger:
        return audit_logger

    async def _override_escalation() -> HumanEscalationManager:
        return escalation_manager

    app.dependency_overrides[deps.get_registry] = lambda: registry
    app.dependency_overrides[deps.get_state_manager] = _override_state_manager
    app.dependency_overrides[deps.get_audit_logger] = _override_audit_logger
    app.dependency_overrides[deps.get_escalation_manager] = _override_escalation
    app.dependency_overrides[deps.get_db_session] = _override_get_db_session

    with TestClient(app) as client:
        yield client


def test_health_endpoint_returns_envelope(api_client: TestClient) -> None:
    response = api_client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["error"] is None
    assert body["data"]["status"] == "ok"
    assert body["data"]["workflows_registered"] == 1


def test_start_list_get_pending_and_audit_endpoints(api_client: TestClient) -> None:
    start = api_client.post(
        "/api/workflows/start",
        json={"workflow_type": "procurement", "input_data": {"vendor_data": _vendor_data()}},
    )
    assert start.status_code == 200
    workflow_id = start.json()["data"]["workflow_id"]

    all_runs = api_client.get("/api/workflows")
    assert all_runs.status_code == 200
    assert any(item["id"] == workflow_id for item in all_runs.json()["data"])

    detail = api_client.get(f"/api/workflows/{workflow_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["id"] == workflow_id
    assert detail.json()["data"]["status"] == "PAUSED"

    pending = api_client.get("/api/workflows/pending")
    assert pending.status_code == 200
    assert any(item["workflow_id"] == workflow_id for item in pending.json()["data"])

    audit = api_client.get(f"/api/workflows/{workflow_id}/audit")
    assert audit.status_code == 200
    assert len(audit.json()["data"]) >= 1


def test_decide_invalid_decision_returns_400(api_client: TestClient) -> None:
    start = api_client.post(
        "/api/workflows/start",
        json={"workflow_type": "procurement", "input_data": {"vendor_data": _vendor_data()}},
    )
    workflow_id = start.json()["data"]["workflow_id"]
    response = api_client.post(
        f"/api/workflows/{workflow_id}/decide",
        json={"actor": "HUMAN", "decision": "MAYBE", "notes": "invalid"},
    )
    assert response.status_code == 400
    assert response.json() == {
        "success": False,
        "data": None,
        "error": "Invalid decision. Allowed: APPROVED, REJECTED, REQUEST_MORE_INFO",
    }


def test_unknown_workflow_id_endpoints_return_404(api_client: TestClient) -> None:
    workflow_id = str(uuid4())

    detail = api_client.get(f"/api/workflows/{workflow_id}")
    assert detail.status_code == 404
    assert detail.json()["success"] is False

    decide = api_client.post(
        f"/api/workflows/{workflow_id}/decide",
        json={"actor": "HUMAN", "decision": "APPROVED", "notes": ""},
    )
    assert decide.status_code == 404
    assert decide.json()["success"] is False

    audit = api_client.get(f"/api/workflows/{workflow_id}/audit")
    assert audit.status_code == 404
    assert audit.json()["success"] is False


def test_decide_approved_resumes_and_completes(api_client: TestClient) -> None:
    start = api_client.post(
        "/api/workflows/start",
        json={"workflow_type": "procurement", "input_data": {"vendor_data": _vendor_data()}},
    )
    workflow_id = start.json()["data"]["workflow_id"]

    decide = api_client.post(
        f"/api/workflows/{workflow_id}/decide",
        json={"actor": "HUMAN", "decision": "APPROVED", "notes": "approved"},
    )
    assert decide.status_code == 200
    assert decide.json()["success"] is True
    assert decide.json()["data"]["result"]["status"] == "COMPLETED"
    assert decide.json()["data"]["result"]["crm_record_id"] is not None


def test_malformed_request_body_returns_400_envelope(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/workflows/start",
        data="{this-is-not-json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json() == {
        "success": False,
        "data": None,
        "error": "Invalid request payload",
    }


def test_missing_required_fields_return_400_envelope(api_client: TestClient) -> None:
    response = api_client.post("/api/workflows/start", json={"input_data": {"vendor_data": _vendor_data()}})
    assert response.status_code == 400
    assert response.json() == {
        "success": False,
        "data": None,
        "error": "Invalid request payload",
    }
