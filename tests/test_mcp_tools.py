"""Tests for MCP tool handlers.

Tests each tool handler by mocking the WorkflowAPIClient.
Handlers are imported from mcp-server/tools/ and tested directly
without starting the MCP server or FastAPI gateway.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add mcp-server/ to sys.path so we can import client and tools modules
MCP_SERVER_DIR = str(Path(__file__).resolve().parent.parent / "mcp-server")
if MCP_SERVER_DIR not in sys.path:
    sys.path.insert(0, MCP_SERVER_DIR)

from tools.start_workflow import handle_start_workflow
from tools.get_status import handle_get_status
from tools.submit_decision import handle_submit_decision
from tools.get_audit_trail import handle_get_audit_trail


# ─── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def mock_api_client():
    """Returns a MagicMock that replaces WorkflowAPIClient."""
    with patch("client.WorkflowAPIClient") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


# ─── start_workflow tests ───────────────────────────────────────────────────

class TestStartWorkflow:
    """Tests for the start_workflow MCP tool handler."""

    @pytest.mark.asyncio
    async def test_success_returns_key_value_pairs(self, mock_api_client: MagicMock):
        """Success path returns workflow_id, status, current_stage."""
        mock_api_client.start_workflow.return_value = {
            "success": True,
            "data": {
                "workflow_id": "wf-abc-123",
                "result": {"status": "PAUSED", "current_stage": "human_review"},
            },
            "error": None,
        }
        result = await handle_start_workflow(
            workflow_type="compliance_review",
            payload='{"document_id": "doc-1"}',
        )
        assert "workflow_id: wf-abc-123" in result
        assert "status: PAUSED" in result
        assert "current_stage: human_review" in result

    @pytest.mark.asyncio
    async def test_api_error_returns_error_message(self, mock_api_client: MagicMock):
        """Non-2xx API response returns error prefix, not stack trace."""
        from client import WorkflowAPIError

        mock_api_client.start_workflow.side_effect = WorkflowAPIError(
            status_code=400, detail="Invalid workflow type"
        )
        result = await handle_start_workflow(
            workflow_type="invalid_type",
            payload="{}",
        )
        assert result.startswith("error:")
        assert "Invalid workflow type" in result

    @pytest.mark.asyncio
    async def test_invalid_json_payload_returns_error(self, mock_api_client: MagicMock):
        """Malformed JSON in payload returns error without calling API."""
        result = await handle_start_workflow(
            workflow_type="compliance_review",
            payload="not-json",
        )
        assert result.startswith("error:")
        assert "Invalid JSON" in result
        mock_api_client.start_workflow.assert_not_called()


# ─── get_status tests ───────────────────────────────────────────────────────

class TestGetStatus:
    """Tests for the get_status MCP tool handler."""

    @pytest.mark.asyncio
    async def test_success_returns_all_fields(self, mock_api_client: MagicMock):
        """Success path returns workflow_id, status, current_stage, created_at."""
        mock_api_client.get_workflow_status.return_value = {
            "success": True,
            "data": {
                "id": "wf-abc-123",
                "status": "RUNNING",
                "current_stage": "severity_assessment",
                "created_at": "2026-05-23T17:00:00Z",
            },
            "error": None,
        }
        result = await handle_get_status(workflow_id="wf-abc-123")
        assert "workflow_id: wf-abc-123" in result
        assert "status: RUNNING" in result
        assert "current_stage: severity_assessment" in result
        assert "created_at: 2026-05-23T17:00:00Z" in result

    @pytest.mark.asyncio
    async def test_api_error_returns_error_message(self, mock_api_client: MagicMock):
        """Non-2xx API response returns error prefix."""
        from client import WorkflowAPIError

        mock_api_client.get_workflow_status.side_effect = WorkflowAPIError(
            status_code=404, detail="Workflow not found"
        )
        result = await handle_get_status(workflow_id="nonexistent")
        assert result.startswith("error:")
        assert "Workflow not found" in result


# ─── submit_decision tests ──────────────────────────────────────────────────

class TestSubmitDecision:
    """Tests for the submit_decision MCP tool handler."""

    @pytest.mark.asyncio
    async def test_approve_returns_new_status(self, mock_api_client: MagicMock):
        """APPROVE decision returns workflow_id and new_status."""
        mock_api_client.submit_decision.return_value = {
            "success": True,
            "data": {
                "workflow_id": "wf-abc-123",
                "result": {"status": "APPROVED"},
            },
            "error": None,
        }
        result = await handle_submit_decision(
            workflow_id="wf-abc-123",
            decision="APPROVE",
            reason="Looks good",
        )
        assert "workflow_id: wf-abc-123" in result
        assert "new_status: APPROVED" in result

    @pytest.mark.asyncio
    async def test_reject_returns_rejected_status(self, mock_api_client: MagicMock):
        """REJECT decision returns workflow_id and REJECTED status."""
        mock_api_client.submit_decision.return_value = {
            "success": True,
            "data": {
                "workflow_id": "wf-abc-123",
                "result": {"status": "REJECTED"},
            },
            "error": None,
        }
        result = await handle_submit_decision(
            workflow_id="wf-abc-123",
            decision="REJECT",
            reason="Missing documentation",
        )
        assert "workflow_id: wf-abc-123" in result
        assert "new_status: REJECTED" in result

    @pytest.mark.asyncio
    async def test_invalid_decision_value_returns_error(self, mock_api_client: MagicMock):
        """Invalid decision (not APPROVE/REJECT) returns error without calling API."""
        result = await handle_submit_decision(
            workflow_id="wf-abc-123",
            decision="INVALID",
        )
        assert result.startswith("error:")
        assert "APPROVE or REJECT" in result
        mock_api_client.submit_decision.assert_not_called()

    @pytest.mark.asyncio
    async def test_api_error_returns_error_message(self, mock_api_client: MagicMock):
        """Non-2xx API response returns error prefix."""
        from client import WorkflowAPIError

        mock_api_client.submit_decision.side_effect = WorkflowAPIError(
            status_code=409, detail="Workflow is not paused"
        )
        result = await handle_submit_decision(
            workflow_id="wf-abc-123",
            decision="APPROVE",
        )
        assert result.startswith("error:")
        assert "Workflow is not paused" in result


# ─── get_audit_trail tests ──────────────────────────────────────────────────

class TestGetAuditTrail:
    """Tests for the get_audit_trail MCP tool handler."""

    @pytest.mark.asyncio
    async def test_success_returns_ordered_events(self, mock_api_client: MagicMock):
        """Success path returns one event per line with pipe-delimited fields."""
        mock_api_client.get_audit_trail.return_value = {
            "success": True,
            "data": [
                {
                    "timestamp": "2026-05-23T17:00:00Z",
                    "actor": "SYSTEM",
                    "event_type": "workflow_started",
                    "stage": "intake",
                },
                {
                    "timestamp": "2026-05-23T17:01:00Z",
                    "actor": "HUMAN",
                    "event_type": "decision_submitted",
                    "stage": "human_review",
                },
            ],
            "error": None,
        }
        result = await handle_get_audit_trail(workflow_id="wf-abc-123")
        lines = result.strip().split("\n")
        assert len(lines) == 2
        assert "SYSTEM" in lines[0]
        assert "workflow_started" in lines[0]
        assert "intake" in lines[0]
        assert "HUMAN" in lines[1]
        assert "decision_submitted" in lines[1]
        assert "human_review" in lines[1]

    @pytest.mark.asyncio
    async def test_empty_trail_returns_no_events_message(self, mock_api_client: MagicMock):
        """Empty audit trail returns 'No audit events found' message."""
        mock_api_client.get_audit_trail.return_value = {
            "success": True,
            "data": [],
            "error": None,
        }
        result = await handle_get_audit_trail(workflow_id="wf-empty")
        assert "No audit events found" in result

    @pytest.mark.asyncio
    async def test_api_error_returns_error_message(self, mock_api_client: MagicMock):
        """Non-2xx API response returns error prefix."""
        from client import WorkflowAPIError

        mock_api_client.get_audit_trail.side_effect = WorkflowAPIError(
            status_code=404, detail="Workflow not found"
        )
        result = await handle_get_audit_trail(workflow_id="nonexistent")
        assert result.startswith("error:")
        assert "Workflow not found" in result
