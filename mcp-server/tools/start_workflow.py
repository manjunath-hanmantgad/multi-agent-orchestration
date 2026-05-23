"""MCP tool: start_workflow.

Calls POST /api/workflows/start on the FastAPI gateway.
Returns workflow_id, status, and current_stage as plain text.
"""

import json

import client


async def handle_start_workflow(workflow_type: str, payload: str = "{}") -> str:
    """Start a new workflow run.

    Starts a workflow of the specified type with the given JSON payload.
    Returns workflow_id, status (PENDING/RUNNING/PAUSED/APPROVED/REJECTED/COMPLETED),
    and current_stage of the newly started workflow.

    Args:
        workflow_type: Type of workflow to start (e.g. compliance_review, incident_triage)
        payload: JSON string with workflow input data (default: {})
    """
    try:
        payload_dict = json.loads(payload) if payload else {}
    except json.JSONDecodeError:
        return "error: Invalid JSON in payload"

    try:
        api = client.WorkflowAPIClient()
        result = api.start_workflow(
            {"workflow_type": workflow_type, "payload": payload_dict}
        )
        return (
            f"workflow_id: {result.get('workflow_id', 'unknown')}\n"
            f"status: {result.get('status', 'unknown')}\n"
            f"current_stage: {result.get('current_stage', 'unknown')}"
        )
    except client.WorkflowAPIError as e:
        return f"error: {e.detail}"
