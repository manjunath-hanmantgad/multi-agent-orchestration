"""MCP tool: get_status.

Calls GET /api/workflows/{workflow_id} on the FastAPI gateway.
Returns workflow_id, status, current_stage, and created_at as plain text.
"""

import client


async def handle_get_status(workflow_id: str) -> str:
    """Get the current status of a workflow.

    Returns workflow_id, status (PENDING/RUNNING/PAUSED/APPROVED/REJECTED/COMPLETED),
    current_stage, and created_at timestamp for the specified workflow.

    Args:
        workflow_id: UUID of the workflow to query
    """
    try:
        result = client.WorkflowAPIClient().get_workflow_status(workflow_id)
        return (
            f"workflow_id: {result.get('workflow_id', 'unknown')}\n"
            f"status: {result.get('status', 'unknown')}\n"
            f"current_stage: {result.get('current_stage', 'unknown')}\n"
            f"created_at: {result.get('created_at', 'unknown')}"
        )
    except client.WorkflowAPIError as e:
        return f"error: {e.detail}"
