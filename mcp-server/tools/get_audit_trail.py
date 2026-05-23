"""MCP tool: get_audit_trail.

Calls GET /api/workflows/{workflow_id}/audit on the FastAPI gateway.
Returns the ordered event list as plain text, one event per line:
    timestamp | actor | event_type | stage
"""

import client


async def handle_get_audit_trail(workflow_id: str) -> str:
    """Retrieve the ordered audit trail for a workflow.

    Returns a timeline of all events recorded for the specified workflow.
    Each event is formatted as: timestamp | actor | event_type | stage.
    Events are ordered chronologically from earliest to latest.

    Args:
        workflow_id: UUID of the workflow to audit
    """
    try:
        result = client.WorkflowAPIClient().get_audit_trail(workflow_id)

        # The API returns {"success": true, "data": [...]}
        data = result.get("data", []) if isinstance(result, dict) else result

        if not data:
            return "No audit events found for this workflow."

        lines = []
        for event in data:
            ts = event.get("timestamp", "unknown")
            actor = event.get("actor", "unknown")
            event_type = event.get("event_type", "unknown")
            stage = event.get("stage", "unknown")
            lines.append(f"{ts} | {actor} | {event_type} | {stage}")

        return "\n".join(lines)
    except client.WorkflowAPIError as e:
        return f"error: {e.detail}"
