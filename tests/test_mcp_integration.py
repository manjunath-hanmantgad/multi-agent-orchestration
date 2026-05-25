"""Integration test: MCP tool handlers calling real FastAPI gateway via TestClient.

The FastAPI gateway runs through starlette's TestClient (ASGI-in-process, no
separate HTTP server). The WorkflowAPIClient's httpx calls are redirected to
the TestClient so MCP tool handlers exercise the real dependency-injected
FastAPI endpoints.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Add mcp-server/ to sys.path so we can import tool handlers
MCP_SERVER_DIR = str(Path(__file__).resolve().parents[1] / "mcp-server")
if MCP_SERVER_DIR not in sys.path:
    sys.path.insert(0, MCP_SERVER_DIR)

from api.dependencies import (
    get_audit_logger,
    get_db_session,
    get_escalation_manager,
    get_registry,
    get_state_manager,
)
from api.routers import approvals, audit, workflows
from core.audit import AuditLogger
from core.escalation import HumanEscalationManager
from core.registry import WorkflowRegistry
from core.state import StateManager
from tools.get_audit_trail import handle_get_audit_trail
from tools.get_status import handle_get_status
from tools.start_workflow import handle_start_workflow
from workflows.compliance_review.agents import ComplianceReviewAgents
from workflows.compliance_review.workflow import ComplianceReviewWorkflow


# ─── Fixture — builds FastAPI gateway + patches MCP client ──────────────────


@pytest.fixture
def mcp_test_client(
    in_memory_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> str:
    """Build FastAPI app with test overrides, create TestClient, and
    monkeypatch WorkflowAPIClient._request to route through TestClient."""
    state_manager = StateManager(session_factory=in_memory_session_factory)
    audit_logger = AuditLogger(session_factory=in_memory_session_factory)
    escalation_manager = HumanEscalationManager(
        state_manager=state_manager, audit_logger=audit_logger
    )

    agents = ComplianceReviewAgents(
        state_manager=state_manager,
        audit_logger=audit_logger,
        escalation_manager=escalation_manager,
        risk_scorer=lambda _results: {
            "risk_score": 50,
            "risk_reasoning": "Mock risk score for integration test",
        },
    )
    workflow = ComplianceReviewWorkflow(
        agents=agents,
        state_manager=state_manager,
        checkpointer=MemorySaver(),
    )
    registry = WorkflowRegistry(auto_discover=False)
    registry.register(workflow)

    app = FastAPI()
    app.include_router(workflows.router, prefix="/api/workflows", tags=["workflows"])
    app.include_router(approvals.router, prefix="/api/workflows", tags=["approvals"])
    app.include_router(audit.router, prefix="/api/workflows", tags=["audit"])

    async def _override_get_db_session():
        async with in_memory_session_factory() as session:
            yield session

    app.dependency_overrides[get_registry] = lambda: registry
    app.dependency_overrides[get_state_manager] = lambda: state_manager
    app.dependency_overrides[get_audit_logger] = lambda: audit_logger
    app.dependency_overrides[get_escalation_manager] = lambda: escalation_manager
    app.dependency_overrides[get_db_session] = _override_get_db_session

    # Create a FastAPI TestClient — wraps ASGI for sync httpx
    tc = TestClient(app)

    # Monkeypatch WorkflowAPIClient._request to route through TestClient
    from client import WorkflowAPIError, WorkflowAPIClient

    def _tc_request(self, method, path, **kwargs):
        # Build the full URL then strip the base for TestClient
        url = f"{self.base_url}{path}"
        # TestClient expects relative paths like /api/workflows/start
        relative_path = path
        json_body = kwargs.pop("json", None)
        data = kwargs.pop("data", None)
        headers = kwargs.pop("headers", self._headers())
        resp = tc.request(method, relative_path, json=json_body, data=data, headers=headers)
        if not resp.is_success:
            detail = resp.text[:500] if resp.text else f"HTTP {resp.status_code}"
            raise WorkflowAPIError(resp.status_code, detail)
        return resp.json()

    monkeypatch.setattr(WorkflowAPIClient, "_request", _tc_request)
    monkeypatch.setenv("WORKFLOW_API_BASE_URL", "http://test")

    yield "http://test"


# ─── Integration test ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_tools_compliance_workflow_full_cycle(
    mcp_test_client: str,
    tmp_path: Path,
) -> None:
    """Run a compliance_review workflow through MCP tool handlers.

    Calls start_workflow, get_status, and get_audit_trail in sequence,
    asserting each returns the expected plain-text key: value format.
    All calls go through the real FastAPI app via TestClient ASGI bridge.
    """
    workflow_id = str(uuid4())
    document_path = tmp_path / "compliance_case.txt"
    document_path.write_text(
        "Entity Name: Test Corp\n"
        "Country: IN\n"
        "Annual Revenue: 1000000\n",
        encoding="utf-8",
    )

    payload = json.dumps(
        {"workflow_id": workflow_id, "document_path": str(document_path)}
    )

    # ── Step 1: start_workflow ──────────────────────────────────────────
    start_result = await handle_start_workflow(
        workflow_type="compliance_review",
        payload=payload,
    )
    assert "workflow_id:" in start_result, f"Missing workflow_id: {start_result}"
    assert workflow_id in start_result
    assert "status:" in start_result
    assert "PAUSED" in start_result, f"Expected PAUSED: {start_result}"
    assert "current_stage:" in start_result

    # ── Step 2: get_status ──────────────────────────────────────────────
    status_result = await handle_get_status(workflow_id=workflow_id)
    assert "workflow_id:" in status_result
    assert workflow_id in status_result
    assert "status:" in status_result
    assert "PAUSED" in status_result, f"Expected PAUSED: {status_result}"
    assert "current_stage:" in status_result
    assert "created_at:" in status_result

    # ── Step 3: get_audit_trail ─────────────────────────────────────────
    audit_result = await handle_get_audit_trail(workflow_id=workflow_id)
    assert audit_result, f"Empty audit trail: {audit_result}"

    lines = audit_result.strip().split("\n")
    assert len(lines) >= 3, f"Expected >=3 audit events, got {len(lines)}"

    for line in lines:
        assert "|" in line, f"Audit event missing pipe-delimiters: {line!r}"

    event_types_found = set()
    stage_names_found = set()
    for line in lines:
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 3:
            event_types_found.add(parts[2])
        if len(parts) >= 4:
            stage_names_found.add(parts[3])

    assert event_types_found, "No event types found in audit lines"
    assert stage_names_found, "No stage names found in audit lines — check audit line format"
    # At least one recognisable stage name must be present (not just event types)
    known_stages = {"intake", "severity_assessment", "risk_assessment", "human_review",
                    "human_approval", "resolution_report", "document_extraction",
                    "rule_evaluation", "risk_scoring"}
    assert stage_names_found & known_stages, (
        f"No known stage names in audit trail. Found: {stage_names_found}"
    )
