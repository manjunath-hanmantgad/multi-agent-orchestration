"""Report generation service for workflow outcomes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID


class ReportGenerationError(RuntimeError):
    """Raised when report generation fails."""


class ReportGenerator:
    """Generates structured JSON reports to outputs directory."""

    def __init__(self, outputs_root: str = "outputs") -> None:
        self._outputs_root = Path(outputs_root)

    def generate_compliance_report(self, workflow_run: Any, audit_trail: list[dict[str, Any]]) -> str:
        """Generate and persist compliance approval report."""
        report = _base_report("compliance", workflow_run, audit_trail)
        report["outcome"] = "APPROVED"
        return self._write_report(report)

    def generate_rejection_report(
        self,
        workflow_run: Any,
        reason: str,
        audit_trail: list[dict[str, Any]],
    ) -> str:
        """Generate and persist rejection report."""
        report = _base_report("rejection", workflow_run, audit_trail)
        report["outcome"] = "REJECTED"
        report["reason"] = reason
        return self._write_report(report)

    def _write_report(self, report: dict[str, Any]) -> str:
        """Write report dictionary to outputs/<workflow_id>/report.json."""
        workflow_id = str(report["workflow_id"])
        output_dir = self._outputs_root / workflow_id
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / "report.json"
        try:
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        except OSError as exc:
            raise ReportGenerationError(f"Failed to write report: {report_path}") from exc
        return str(report_path)


def _base_report(report_type: str, workflow_run: Any, audit_trail: list[dict[str, Any]]) -> dict[str, Any]:
    """Build common report payload shape."""
    run = _to_serializable(workflow_run)
    workflow_id = run.get("id") or run.get("workflow_id")
    if not workflow_id:
        raise ReportGenerationError("workflow_run must include id")
    return {
        "report_type": report_type,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "workflow_id": str(workflow_id),
        "workflow_run": run,
        "audit_trail": [_to_serializable(item) for item in audit_trail],
    }


def _to_serializable(value: Any) -> Any:
    """Recursively normalize value to JSON-serializable data."""
    if hasattr(value, "model_dump"):
        return _to_serializable(value.model_dump())
    if isinstance(value, dict):
        return {str(key): _to_serializable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_serializable(item) for item in value]
    if isinstance(value, tuple):
        return [_to_serializable(item) for item in value]
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if hasattr(value, "value"):
        return _to_serializable(value.value)
    return value
