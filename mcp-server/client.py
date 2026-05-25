"""Thin httpx wrapper for calling the FastAPI gateway.

Usage:
    client = WorkflowAPIClient()
    result = client.start_workflow({"workflow_type": "compliance_review", ...})
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx


class WorkflowAPIError(Exception):
    """Raised when the FastAPI gateway returns a non-2xx response."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"WorkflowAPIError {status_code}: {detail}")


class WorkflowAPIClient:
    """HTTP client for the FastAPI workflow gateway.

    Base URL from WORKFLOW_API_BASE_URL env var (default: http://127.0.0.1:8000).
    Optional bearer token from WORKFLOW_API_TOKEN env var.
    """

    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.base_url = (base_url or os.getenv("WORKFLOW_API_BASE_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.token = token or os.getenv("WORKFLOW_API_TOKEN", "") or None
        self._timeout = 30.0

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self._timeout) as client:
            response = client.request(method, url, headers=self._headers(), **kwargs)
            if not response.is_success:
                detail = response.text[:500] if response.text else f"HTTP {response.status_code}"
                raise WorkflowAPIError(response.status_code, detail)
            return response.json()

    def start_workflow(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Start a new workflow run.

        POST /api/workflows/start
        """
        return self._request("POST", "/api/workflows/start", json=payload)

    def get_workflow_status(self, workflow_id: str) -> Dict[str, Any]:
        """Get current workflow status and stage.

        GET /api/workflows/{workflow_id}
        """
        return self._request("GET", f"/api/workflows/{workflow_id}")

    def submit_decision(self, workflow_id: str, decision: str, reason: str | None = None) -> Dict[str, Any]:
        """Submit a human approval or rejection decision.

        POST /api/workflows/{workflow_id}/decide
        """
        payload: Dict[str, Any] = {"actor": "HUMAN", "decision": decision, "notes": reason or ""}
        return self._request("POST", f"/api/workflows/{workflow_id}/decide", json=payload)

    def get_audit_trail(self, workflow_id: str) -> Dict[str, Any]:
        """Retrieve the ordered audit trail for a workflow.

        GET /api/workflows/{workflow_id}/audit
        """
        return self._request("GET", f"/api/workflows/{workflow_id}/audit")

    def health_check(self) -> bool:
        """Check if the FastAPI gateway is reachable.

        GET /api/health
        Returns True if the gateway responds with 2xx, False otherwise.
        """
        try:
            self._request("GET", "/api/health")
            return True
        except (WorkflowAPIError, httpx.RequestError, httpx.TimeoutException):
            return False
