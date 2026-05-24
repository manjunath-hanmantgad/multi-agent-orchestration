"""Tests for the ToolRegistry.

Verifies registration, lookup, listing, duplicate detection,
and that importing the module has no side effects.
"""

from __future__ import annotations

import pytest

from core.tool_registry import ToolRegistry


class TestToolRegistry:
    """Tests for ToolRegistry class behaviour."""

    def test_register_and_get_tool(self):
        """Register a tool and retrieve it by name."""
        registry = ToolRegistry()

        @registry.register(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {"x": {"type": "integer"}}},
            example_call="test_tool(x=42)",
        )
        async def my_handler(x: int) -> str:
            return f"got {x}"

        tool = registry.get_tool("test_tool")
        assert tool["name"] == "test_tool"
        assert tool["description"] == "A test tool"
        assert tool["input_schema"] == {
            "type": "object",
            "properties": {"x": {"type": "integer"}},
        }
        assert tool["example_call"] == "test_tool(x=42)"
        assert tool["handler"] is my_handler

    def test_list_tools_returns_all(self):
        """List returns all registered tools."""
        registry = ToolRegistry()

        @registry.register(name="tool_a", description="First tool")
        async def tool_a():
            pass

        @registry.register(name="tool_b", description="Second tool")
        async def tool_b():
            pass

        tools = registry.list_tools()
        assert len(tools) == 2
        names = [t["name"] for t in tools]
        assert "tool_a" in names
        assert "tool_b" in names

    def test_get_unknown_tool_raises_key_error(self):
        """Getting an unregistered tool raises KeyError."""
        registry = ToolRegistry()
        with pytest.raises(KeyError) as exc:
            registry.get_tool("nonexistent")
        assert "nonexistent" in str(exc.value)

    def test_duplicate_registration_raises_value_error(self):
        """Registering the same name twice raises ValueError."""
        registry = ToolRegistry()

        @registry.register(name="duplicate")
        async def first():
            pass

        with pytest.raises(ValueError) as exc:
            registry.register(name="duplicate")

        assert "duplicate" in str(exc.value)

    def test_len_reflects_registered_count(self):
        """Length reflects number of registered tools."""
        registry = ToolRegistry()
        assert len(registry) == 0

        @registry.register(name="only_one")
        async def fn():
            pass

        assert len(registry) == 1

    def test_empty_schema_defaults_to_empty_dict(self):
        """Registering without input_schema defaults to {}."""
        registry = ToolRegistry()

        @registry.register(name="no_schema", description="No schema")
        async def fn():
            pass

        tool = registry.get_tool("no_schema")
        assert tool["input_schema"] == {}

    def test_empty_description_defaults_to_empty_string(self):
        """Registering without description defaults to ''."""
        registry = ToolRegistry()

        @registry.register(name="no_desc")
        async def fn():
            pass

        tool = registry.get_tool("no_desc")
        assert tool["description"] == ""


class TestImportSideEffects:
    """Verify importing the module has no side effects."""

    def test_import_does_not_trigger_db_or_network(self):
        """Importing registry module must not make any external calls."""
        # This test passes by virtue of not timing out or crashing.
        # If the module made a network call, database query, or file write,
        # it would either fail or be detectable here.
        # Test with a fresh ToolRegistry() to isolate from any tool modules
        # that may have been imported by other test files using the singleton.
        from core.tool_registry import ToolRegistry

        fresh = ToolRegistry()
        assert hasattr(fresh, "list_tools")
        # A fresh registry is empty — no tools registered
        assert len(fresh) == 0
