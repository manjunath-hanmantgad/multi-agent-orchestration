"""Tests for document parsing, rules, notifications, and reporting services."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from core.models import WorkflowRun, WorkflowStatus
from core.services.document_parser import DocumentParser, UnsupportedFileTypeError
from core.services.notification import NotificationService
from core.services.report_generator import ReportGenerator
from core.services.rule_engine import RuleEngine


def test_document_parser_extracts_pdf_and_docx_fixture_text() -> None:
    """Parser extracts text and metadata from sample PDF and DOCX fixtures."""
    parser = DocumentParser()

    pdf_result = parser.parse("tests/fixtures/sample_document.pdf")
    assert "Meridian Supplies Ltd" in pdf_result["text"]
    assert pdf_result["metadata"]["file_type"] == "pdf"
    assert pdf_result["metadata"]["page_count"] == 1

    docx_result = parser.parse("tests/fixtures/sample_document.docx")
    assert "Compliance Declaration" in docx_result["text"]
    assert docx_result["metadata"]["file_type"] == "docx"
    assert docx_result["metadata"]["page_count"] >= 1


def test_document_parser_unsupported_file_type_raises(tmp_path: Path) -> None:
    """Unsupported file extensions raise UnsupportedFileTypeError."""
    parser = DocumentParser()
    unknown = tmp_path / "input.csv"
    unknown.write_text("a,b,c", encoding="utf-8")

    with pytest.raises(UnsupportedFileTypeError):
        parser.parse(str(unknown))


def test_rule_engine_evaluates_equals_contains_and_greater_than(tmp_path: Path) -> None:
    """RuleEngine correctly classifies three required operator types."""
    workflow_name = "compliance_demo"
    workflow_dir = tmp_path / workflow_name
    workflow_dir.mkdir(parents=True)
    rules = [
        {
            "id": "R1",
            "name": "Country check",
            "description": "country must equal IN",
            "field": "country",
            "operator": "equals",
            "value": "IN",
            "severity": "high",
        },
        {
            "id": "R2",
            "name": "Statement marker",
            "description": "text contains mandatory declaration",
            "field": "statement",
            "operator": "contains",
            "value": "declaration",
            "severity": "low",
        },
        {
            "id": "R3",
            "name": "Net worth threshold",
            "description": "net_worth > 1000000",
            "field": "net_worth",
            "operator": "greater_than",
            "value": 1000000,
            "severity": "critical",
        },
    ]
    (workflow_dir / "rules.json").write_text(json.dumps(rules), encoding="utf-8")

    engine = RuleEngine(workflows_root=str(tmp_path))
    loaded = engine.load_rules(workflow_name)
    results = engine.evaluate(
        {
            "country": "IN",
            "statement": "This declaration is signed.",
            "net_worth": 1500000,
        },
        loaded,
    )

    assert len(results["passed"]) == 3
    assert results["failed"] == []
    assert results["flagged"] == []


def test_notification_service_never_raises_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Notification service returns False and suppresses HTTP errors."""
    service = NotificationService(webhook_url="https://example.invalid/webhook")

    def _raise(*args: object, **kwargs: object) -> None:
        raise httpx.ConnectError("network failure")

    monkeypatch.setattr(httpx, "post", _raise)
    assert service.notify_reviewer("wf-1", "compliance_review", "needs review") is False


def test_notification_service_skips_when_webhook_missing() -> None:
    """Notification service silently skips when webhook URL is not configured."""
    service = NotificationService(webhook_url="")
    assert service.notify_reviewer("wf-2", "procurement", "pending") is False


def test_report_generator_creates_json_report_at_expected_path(tmp_path: Path) -> None:
    """ReportGenerator writes valid report JSON under outputs/<workflow_id>/report.json."""
    workflow_id = uuid4()
    workflow_run = WorkflowRun(
        id=workflow_id,
        workflow_type="compliance_review",
        status=WorkflowStatus.APPROVED,
        current_stage="certificate",
        payload={"checkpoint_data": {"risk_score": 20}},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    generator = ReportGenerator(outputs_root=str(tmp_path / "outputs"))
    report_path = generator.generate_compliance_report(
        workflow_run,
        [{"event_type": "DECISION_SUBMITTED", "actor": "HUMAN"}],
    )

    expected_path = tmp_path / "outputs" / str(workflow_id) / "report.json"
    assert Path(report_path) == expected_path
    data = json.loads(expected_path.read_text(encoding="utf-8"))
    assert data["workflow_id"] == str(workflow_id)
    assert data["outcome"] == "APPROVED"


def test_report_generator_rejection_report_contains_reason(tmp_path: Path) -> None:
    """Rejection report includes reason and rejection outcome."""
    workflow_id = uuid4()
    generator = ReportGenerator(outputs_root=str(tmp_path / "outputs"))

    report_path = generator.generate_rejection_report(
        workflow_run={"id": str(workflow_id), "workflow_type": "compliance_review"},
        reason="Missing tax declaration",
        audit_trail=[],
    )

    data = json.loads(Path(report_path).read_text(encoding="utf-8"))
    assert data["outcome"] == "REJECTED"
    assert data["reason"] == "Missing tax declaration"
