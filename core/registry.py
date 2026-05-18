"""Workflow registry and plugin module discovery."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class WorkflowNotFoundError(LookupError):
    """Raised when a workflow cannot be found in the registry."""


class WorkflowModule(ABC):
    """Base interface for pluggable workflow modules."""

    name: str
    description: str

    @abstractmethod
    def build_graph(self) -> Any:
        """Build and return the workflow graph."""

    @abstractmethod
    def get_input_schema(self) -> dict[str, Any]:
        """Return serializable input schema metadata."""


@dataclass(frozen=True)
class _WorkflowDescriptor:
    """Internal immutable workflow descriptor."""

    name: str
    description: str
    module: WorkflowModule


class WorkflowRegistry:
    """Registry for discovering and retrieving workflow modules."""

    def __init__(self, base_package: str = "workflows", auto_discover: bool = True) -> None:
        self._base_package = base_package
        self._modules: dict[str, _WorkflowDescriptor] = {}
        if auto_discover:
            self.auto_discover()

    def register(self, module: WorkflowModule) -> None:
        """Register a workflow module instance."""
        if not isinstance(module, WorkflowModule):
            raise TypeError("module must be an instance of WorkflowModule")
        if not module.name:
            raise ValueError("workflow module name must not be empty")
        if not module.description:
            raise ValueError("workflow module description must not be empty")
        self._modules[module.name] = _WorkflowDescriptor(
            name=module.name,
            description=module.description,
            module=module,
        )

    def get(self, name: str) -> WorkflowModule:
        """Return a registered workflow module by name."""
        descriptor = self._modules.get(name)
        if descriptor is None:
            raise WorkflowNotFoundError(f"Workflow not found: {name}")
        return descriptor.module

    def list_workflows(self) -> list[dict[str, str]]:
        """List available workflow names and descriptions."""
        return [
            {"name": entry.name, "description": entry.description}
            for entry in sorted(self._modules.values(), key=lambda item: item.name)
        ]

    def auto_discover(self) -> None:
        """Auto-discover workflow modules from workflow package folders."""
        package = self._import_base_package()
        if package is None or not hasattr(package, "__path__"):
            return
        for _, package_name, is_package in pkgutil.iter_modules(package.__path__):
            if is_package:
                self._discover_from_subpackage(package_name)

    def _import_base_package(self) -> Any | None:
        """Import configured base package and return None if missing."""
        try:
            return importlib.import_module(self._base_package)
        except ModuleNotFoundError:
            return None

    def _discover_from_subpackage(self, package_name: str) -> None:
        """Load conventional workflow module file and register discovered modules."""
        module_name = f"{self._base_package}.{package_name}.workflow"
        try:
            imported_module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name == module_name:
                return
            message = (
                f"Failed to import workflow module '{module_name}' because dependency "
                f"'{exc.name}' is missing."
            )
            raise ModuleNotFoundError(message) from exc
        for module in _extract_modules(imported_module):
            self.register(module)


def _extract_modules(imported_module: Any) -> list[WorkflowModule]:
    """Extract workflow module instances from an imported module."""
    discovered: list[WorkflowModule] = []
    for _, value in inspect.getmembers(imported_module):
        if isinstance(value, WorkflowModule):
            discovered.append(value)
            continue
        if inspect.isclass(value) and issubclass(value, WorkflowModule):
            if value is WorkflowModule:
                continue
            discovered.append(value())
    unique: dict[str, WorkflowModule] = {}
    for module in discovered:
        unique[module.name] = module
    return list(unique.values())


registry = WorkflowRegistry()
