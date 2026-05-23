"""MCP tool: submit_decision.

Calls POST /api/workflows/{workflow_id}/decide on the FastAPI gateway.
Returns workflow_id and new_status as plain text.
"""

import client


async def handle_submit_decision(workflow_id: str, decision: str, reason: str = "") -> str:
    """Submit an APPROVE or REJECT decision for a paused workflow.

    Submits a human decision to resume or reject a workflow that is currently
    paused at a human approval stage. Returns workflow_id and new_status
    (APPROVED/REJECTED/COMPLETED/PAUSED).

    Args:
        workflow_id: UUID of the paused workflow
        decision: Either APPROVE or REJECT
        reason: Optional explanation for the decision (required for REJECT)
    """
    if decision not in ("APPROVE", "REJECT"):
        return "error: decision must be APPROVE or REJECT"

    try:
        api = client.WorkflowAPIClient()
        result = api.submit_decision(workflow_id, decision, reason or None)
        return (
            f"workflow_id: {result.get('workflow_id', 'unknown')}\n"
            f"new_status: {result.get('new_status', result.get('status', 'unknown'))}"
        )
    except client.WorkflowAPIError as e:
        return f"error: {e.detail}"
