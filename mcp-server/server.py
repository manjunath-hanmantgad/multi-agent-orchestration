"""MCP Server entry point — STDIO transport.

This server exposes workflow operations as MCP tools to any LLM agent
(Claude Desktop, Claude Code, etc.). It calls the FastAPI gateway over HTTP.

Usage:
    WORKFLOW_API_BASE_URL=http://127.0.0.1:8000 python mcp-server/server.py

IMPORTANT — STDIO transport rule:
When running under STDIO, stdout is the JSON-RPC message channel. Any
print() statement, logging output, or startup banner written to stdout will
corrupt the protocol. ALL diagnostic output must go to stderr.
"""

import logging
import sys
import warnings

# Suppress warnings early — they can write to stdout and corrupt STDIO transport
warnings.filterwarnings("ignore")

# Configure logging to stderr only — never stdout
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("mcp-server")

from pathlib import Path

# Add the parent directory to sys.path so we can import from core/ if needed
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from mcp.server.fastmcp import FastMCP  # noqa: E402

# Create the MCP server instance
# Using FastMCP with STDIO transport (default)
mcp = FastMCP(
    "workflow-orchestrator",
    instructions="Multi-Agent Orchestration Platform — start workflows, check status, submit decisions, and retrieve audit trails.",
    log_level="INFO",
)

# --- Register MCP Tools from registry ---
# Importing each tool module triggers its @registry.register decorator,
# populating the singleton. The loop below then reads the registry as the
# single source of truth — adding a new tool requires only a new module with
# @registry.register; this file needs no change.

from core.tool_registry import registry
import tools.start_workflow   # noqa: F401 — triggers @registry.register
import tools.get_status       # noqa: F401
import tools.submit_decision  # noqa: F401
import tools.get_audit_trail  # noqa: F401

for _tool in registry.list_tools():
    mcp.tool(name=_tool["name"], description=_tool["description"])(_tool["handler"])  # type: ignore[arg-type]


def main():
    """Start the MCP server with STDIO transport.

    Connection errors to the FastAPI gateway are logged but do not prevent
    startup — the server starts and reports availability when the gateway
    becomes reachable.
    """
    logger.info("Starting MCP server (STDIO transport)...")
    logger.info("FastAPI gateway: %s", __import__("os").getenv("WORKFLOW_API_BASE_URL", "http://127.0.0.1:8000"))

    try:
        # Run with STDIO transport (default for FastMCP)
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        logger.info("MCP server stopped via KeyboardInterrupt")
        sys.exit(0)
    except Exception as exc:
        logger.error("MCP server failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
