"""Centralised tool registry for the Multi-Agent Orchestration Platform.

Provides a dict-based catalog of workflow tools that the MCP server reads
at startup to generate its tool list. Tools are registered via a decorator.

IMPORTANT: This module must never import from `workflows/` — workflow modules
import from `core/`, and a reverse import creates a circular dependency.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List


class ToolRegistry:
    """Dict-based catalog of available workflow tools.

    Tools are registered via the `register` decorator at module import time.
    The MCP server reads the registry at startup to generate its tool list.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        name: str,
        description: str = "",
        input_schema: Dict[str, Any] | None = None,
        example_call: str = "",
    ) -> Callable[[Callable], Callable]:
        """Decorator to register a tool in the catalog.

        Args:
            name: Unique tool name (snake_case).
            description: Human-readable description of what the tool does
                and what it returns.
            input_schema: JSON Schema dict describing the tool's input
                parameters.
            example_call: Example invocation string showing how to call
                the tool, e.g. ``start_workflow(workflow_type='compliance_review')``.

        Returns:
            Decorator that registers the function and returns it unchanged.

        Raises:
            ValueError: If a tool with the same name is already registered.
        """
        if name in self._tools:
            raise ValueError(
                f"Tool '{name}' is already registered in the registry"
            )

        def decorator(func: Callable) -> Callable:
            self._tools[name] = {
                "name": name,
                "description": description,
                "input_schema": input_schema or {},
                "example_call": example_call,
                "handler": func,
            }
            return func

        return decorator

    def list_tools(self) -> List[Dict[str, Any]]:
        """Return the full list of registered tool descriptors."""
        return list(self._tools.values())

    def get_tool(self, name: str) -> Dict[str, Any]:
        """Return a single tool descriptor by name.

        Raises:
            KeyError: If no tool with the given name is registered.
        """
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found in registry")
        return self._tools[name]

    def __len__(self) -> int:
        return len(self._tools)


# Module-level singleton — import this from tool modules and MCP server
registry = ToolRegistry()
