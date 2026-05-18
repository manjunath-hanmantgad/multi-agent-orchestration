"""Tests for workflow registry behavior and discovery."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

from core.registry import WorkflowModule, WorkflowNotFoundError, WorkflowRegistry


class MockWorkflow(WorkflowModule):
    """Simple test implementation of WorkflowModule."""

    name = "mock_workflow"
    description = "Mock workflow used for registry tests"

    def build_graph(self) -> Any:
        return {"graph": "mock"}

    def get_input_schema(self) -> dict[str, Any]:
        return {"type": "object"}


def test_register_get_and_list_workflows() -> None:
    """Registry can register modules and list descriptive metadata."""
    registry = WorkflowRegistry(auto_discover=False)
    module = MockWorkflow()

    registry.register(module)

    found = registry.get("mock_workflow")
    assert found is module
    assert registry.list_workflows() == [
        {
            "name": "mock_workflow",
            "description": "Mock workflow used for registry tests",
        }
    ]


def test_get_nonexistent_raises_error() -> None:
    """Unknown workflow names raise WorkflowNotFoundError."""
    registry = WorkflowRegistry(auto_discover=False)

    with pytest.raises(WorkflowNotFoundError, match="Workflow not found"):
        registry.get("nonexistent")


def test_auto_discover_registers_conforming_workflow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Adding a workflow folder with a conforming module is auto-discovered."""
    package_root = tmp_path / "test_workflows"
    workflow_dir = package_root / "invoice_review"

    workflow_dir.mkdir(parents=True)
    (package_root / "__init__.py").write_text('"""test workflow package"""\n', encoding="utf-8")
    (workflow_dir / "__init__.py").write_text('"""invoice workflow"""\n', encoding="utf-8")
    (workflow_dir / "workflow.py").write_text(
        "\n".join(
            [
                "from typing import Any",
                "from core.registry import WorkflowModule",
                "",
                "class InvoiceReviewWorkflow(WorkflowModule):",
                "    name = 'invoice_review'",
                "    description = 'Invoice review workflow'",
                "",
                "    def build_graph(self) -> Any:",
                "        return {'graph': 'invoice'}",
                "",
                "    def get_input_schema(self) -> dict[str, Any]:",
                "        return {'type': 'object'}",
                "",
                "workflow_instance = InvoiceReviewWorkflow()",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.syspath_prepend(str(tmp_path))
    _clear_test_package_modules("test_workflows")
    registry = WorkflowRegistry(base_package="test_workflows", auto_discover=True)

    discovered = registry.get("invoice_review")
    assert discovered.description == "Invoice review workflow"
    assert registry.list_workflows() == [
        {"name": "invoice_review", "description": "Invoice review workflow"}
    ]


def _clear_test_package_modules(base_package: str) -> None:
    """Remove imported modules from a test package to avoid cross-test state."""
    for module_name in list(sys.modules.keys()):
        if module_name == base_package or module_name.startswith(f"{base_package}."):
            sys.modules.pop(module_name, None)
