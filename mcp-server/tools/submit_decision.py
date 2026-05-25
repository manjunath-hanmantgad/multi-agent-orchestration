"""MCP tool: submit_decision.

Calls POST /api/workflows/{workflow_id}/decide on the FastAPI gateway.
Returns workflow_id and new_status as plain text.
"""

import client
from core.tool_registry import registry


@registry.register(
    name="submit_decision",
    description="Submits an APPROVE or REJECT decision for a paused workflow and returns workflow_id and new_status (APPROVED/REJECTED/COMPLETED/PAUSED).",
    input_schema={
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "UUID of the paused workflow",
            },
            "decision": {
                "type": "string",
                "description": "Either APPROVE or REJECT",
                "enum": ["APPROVE", "REJECT"],
            },
            "reason": {
                "type": "string",
                "description": "Optional explanation for the decision (required for REJECT)",
                "default": "",
            },
        },
        "required": ["workflow_id", "decision"],
    },
    example_call='submit_decision(workflow_id="abc-123", decision="APPROVE", reason="All checks passed")',
)
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

    mapped = "APPROVED" if decision == "APPROVE" else "REJECTED"

    try:
        api = client.WorkflowAPIClient()
        result = api.submit_decision(workflow_id, mapped, reason or "")
        data = result.get("data", {})
        inner_result = data.get("result", {})
        return (
            f"workflow_id: {data.get('workflow_id', 'unknown')}\n"
            f"new_status: {inner_result.get('status', 'unknown')}"
        )
    except client.WorkflowAPIError as e:
        return f"error: {e.detail}"
