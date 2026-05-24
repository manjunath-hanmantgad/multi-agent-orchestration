"""MCP tool: start_workflow.

Calls POST /api/workflows/start on the FastAPI gateway.
Returns workflow_id, status, and current_stage as plain text.
"""

import json

import client
from core.tool_registry import registry


@registry.register(
    name="start_workflow",
    description="Starts a new workflow run and returns workflow_id, status (PENDING/RUNNING/PAUSED/APPROVED/REJECTED/COMPLETED), and current_stage.",
    input_schema={
        "type": "object",
        "properties": {
            "workflow_type": {
                "type": "string",
                "description": "Type of workflow to start (e.g. compliance_review, incident_triage)",
            },
            "payload": {
                "type": "string",
                "description": "JSON string with workflow input data (default: {})",
                "default": "{}",
            },
        },
        "required": ["workflow_type"],
    },
    example_call='start_workflow(workflow_type="compliance_review", payload=\'{"document_id": "doc-1"}\')',
)
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
            {"workflow_type": workflow_type, "input_data": payload_dict}
        )
        data = result.get("data", {})
        inner_result = data.get("result", {})
        return (
            f"workflow_id: {data.get('workflow_id', 'unknown')}\n"
            f"status: {inner_result.get('status', 'unknown')}\n"
            f"current_stage: {inner_result.get('current_stage', 'unknown')}"
        )
    except client.WorkflowAPIError as e:
        return f"error: {e.detail}"
