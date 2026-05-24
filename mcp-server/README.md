# MCP Server — Multi-Agent Orchestration Platform

Standalone MCP (Model Context Protocol) server that exposes workflow operations as tools to any LLM agent (Claude Desktop, Claude Code, etc.).

## Architecture

This MCP server runs as a separate process from the FastAPI gateway. It communicates with the gateway over HTTP (not embedded imports), keeping it independently deployable.

```
LLM Agent ───MCP (STDIO)──→ MCP Server ───HTTP──→ FastAPI Gateway (:8000) ───→ LangGraph Engine
```

## Prerequisites

- **Python >= 3.10** (the `mcp` SDK requires it)
- The FastAPI gateway running on `http://127.0.0.1:8000` (or configured via `WORKFLOW_API_BASE_URL`)

## Setup

```bash
# Navigate to the MCP server directory
cd mcp-server

# Create a virtual environment (Python >= 3.10 required)
python3.12 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Running

```bash
# Set the FastAPI gateway URL (default: http://127.0.0.1:8000)
export WORKFLOW_API_BASE_URL=http://127.0.0.1:8000

# Start the MCP server (STDIO transport)
python server.py
```

The server starts immediately. Connection errors to the FastAPI gateway are logged to stderr — the server does not crash if the gateway is not reachable at startup.

## Claude Desktop Configuration

Add the following to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "workflow-orchestrator": {
      "command": "/path/to/mcp-server/venv/bin/python",
      "args": [
        "/absolute/path/to/mcp-server/server.py"
      ],
      "env": {
        "WORKFLOW_API_BASE_URL": "http://127.0.0.1:8000",
        "WORKFLOW_API_TOKEN": ""
      }
    }
  }
}
```

On macOS, the config file is at:
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `WORKFLOW_API_BASE_URL` | No | `http://127.0.0.1:8000` | FastAPI gateway URL |
| `WORKFLOW_API_TOKEN` | No | (empty) | Optional bearer token for API calls |
| `MCP_SERVER_HOST` | No | `127.0.0.1` | Bind host (Streamable HTTP transport only) |
| `MCP_SERVER_PORT` | No | `8012` | Port (Streamable HTTP transport only) |

## Available Tools

| Tool | Description |
|------|-------------|
| `start_workflow` | Starts a new workflow run and returns workflow_id, status, current_stage |
| `get_status` | Returns workflow_id, status (PENDING/RUNNING/PAUSED/APPROVED/REJECTED/COMPLETED), current_stage, and created_at |
| `submit_decision` | Submits an APPROVE/REJECT decision for a paused workflow; returns workflow_id and new_status |
| `get_audit_trail` | Returns the ordered audit event timeline for a workflow as plain text |

## Debugging

All diagnostic output goes to stderr. To see debug logs:

```bash
python server.py 2>&1 | tee mcp-server.log
```

## Production Deployment (Streamable HTTP)

For Azure production deployments, switch to Streamable HTTP transport:

```bash
python server.py --transport streamable-http --host 0.0.0.0 --port 8012
```

This requires `MCP_SERVER_HOST` and `MCP_SERVER_PORT` env vars to be set. Not documented in full here — refer to the MCP Python SDK docs for transport configuration.
