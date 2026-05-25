"""MCP tool: get_status.

Calls GET /api/workflows/{workflow_id} on the FastAPI gateway.
Returns workflow_id, status, current_stage, and created_at as plain text.
"""

import client
from core.tool_registry import registry


@registry.register(
    name="get_status",
    description="Returns workflow_id, status (PENDING/RUNNING/PAUSED/APPROVED/REJECTED/COMPLETED), current_stage, and created_at timestamp for a workflow.",
    input_schema={
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "UUID of the workflow to query",
            },
        },
        "required": ["workflow_id"],
    },
    example_call='get_status(workflow_id="abc-123")',
)
async def handle_get_status(workflow_id: str) -> str:
    """Get the current status of a workflow.

    Returns workflow_id, status (PENDING/RUNNING/PAUSED/APPROVED/REJECTED/COMPLETED),
    current_stage, and created_at timestamp for the specified workflow.

    Args:
        workflow_id: UUID of the workflow to query
    """
    try:
        result = client.WorkflowAPIClient().get_workflow_status(workflow_id)
        data = result.get("data", {})
        return (
            f"workflow_id: {data.get('id', 'unknown')}\n"
            f"status: {data.get('status', 'unknown')}\n"
            f"current_stage: {data.get('current_stage', 'unknown')}\n"
            f"created_at: {data.get('created_at', 'unknown')}"
        )
    except client.WorkflowAPIError as e:
        return f"error: {e.detail}"
