"""Integration tests for compliance review LangGraph workflow."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.audit import AuditLogger
from core.escalation import HumanEscalationManager
from core.services.report_generator import ReportGenerator
from core.services.rule_engine import RuleEngine, RuleEngineError
from core.state import StateManager
from workflows.compliance_review.agents import ComplianceReviewAgents, load_and_validate_rules
from workflows.compliance_review.workflow import ComplianceReviewWorkflow


def _write_case_document(path: Path) -> None:
    """Write fixture document with fields consumed by default rules."""
    path.write_text(
        "\n".join(
            [
                "Entity Name: Meridian Supplies Ltd",
                "Country: IN",
                "Annual Revenue: 2500000",
                "Sanctions Clearance: clear",
                "Tax Declaration: Completed and signed by CFO",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _copy_default_rules(target_root: Path) -> None:
    """Copy default rules file to temporary workflow root for isolated tests."""
    source = Path("workflows/compliance_review/rules.json")
    workflow_dir = target_root / "compliance_review"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    workflow_dir.joinpath("rules.json").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def _build_workflow(
    tmp_path: Path,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    score: int,
) -> tuple[ComplianceReviewWorkflow, AuditLogger]:
    """Construct workflow module wired to isolated DB, outputs, and rules."""
    rules_root = tmp_path / "workflows"
    _copy_default_rules(rules_root)

    state_manager = StateManager(session_factory=session_factory)
    audit_logger = AuditLogger(session_factory=session_factory)
    escalation = HumanEscalationManager(state_manager=state_manager, audit_logger=audit_logger)
    agents = ComplianceReviewAgents(
        state_manager=state_manager,
        audit_logger=audit_logger,
        escalation_manager=escalation,
        rule_engine=RuleEngine(workflows_root=str(rules_root)),
        report_generator=ReportGenerator(outputs_root=str(tmp_path / "outputs")),
        risk_scorer=lambda _results: {
            "risk_score": score,
            "risk_reasoning": f"Deterministic score for test: {score}",
        },
    )
    workflow = ComplianceReviewWorkflow(
        agents=agents,
        state_manager=state_manager,
        checkpointer=MemorySaver(),
    )
    return workflow, audit_logger


@pytest.mark.asyncio
async def test_compliance_workflow_approved_path_runs_end_to_end(
    tmp_path: Path,
    in_memory_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Workflow pauses for review, resumes with APPROVED, and generates report."""
    workflow, audit_logger = _build_workflow(tmp_path, in_memory_session_factory, score=23)
    document_path = tmp_path / "case.txt"
    _write_case_document(document_path)
    workflow_id = str(uuid4())

    paused = await workflow.start({"workflow_id": workflow_id, "document_path": str(document_path)})
    assert paused.status == "PAUSED"
    snapshot = workflow.build_graph().get_state({"configurable": {"thread_id": workflow_id}})
    assert snapshot.next == ("decision_agent",)

    result = await workflow.resume(workflow_id, decision="APPROVED", notes="All checks satisfied")
    assert result.status == "COMPLETED"
    assert result.human_decision == "APPROVED"
    assert result.report_path is not None
    assert Path(result.report_path).exists()

    trail = await audit_logger.get_trail(workflow_id)
    stages = {event["stage"] for event in trail}
    for stage in {
        "intake_agent",
        "rule_check_agent",
        "risk_scoring_agent",
        "human_review_node",
        "decision_agent",
        "certificate_agent",
    }:
        assert stage in stages


@pytest.mark.asyncio
async def test_compliance_workflow_rejected_path_generates_rejection_report(
    tmp_path: Path,
    in_memory_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Rejected decision routes to rejection agent and writes rejection report."""
    workflow, audit_logger = _build_workflow(tmp_path, in_memory_session_factory, score=88)
    document_path = tmp_path / "case.txt"
    _write_case_document(document_path)
    workflow_id = str(uuid4())

    await workflow.start({"workflow_id": workflow_id, "document_path": str(document_path)})
    result = await workflow.resume(workflow_id, decision="REJECTED", notes="Manual policy override")

    assert result.status == "COMPLETED"
    assert result.human_decision == "REJECTED"
    assert result.report_path is not None
    payload = json.loads(Path(result.report_path).read_text(encoding="utf-8"))
    assert payload["outcome"] == "REJECTED"
    assert payload["reason"] == "Manual policy override"

    trail = await audit_logger.get_trail(workflow_id)
    assert any(item["stage"] == "rejection_agent" for item in trail)


@pytest.mark.asyncio
async def test_compliance_workflow_request_more_info_loops_without_state_loss(
    tmp_path: Path,
    in_memory_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """REQUEST_MORE_INFO loops back and pauses again before a final decision."""
    workflow, _ = _build_workflow(tmp_path, in_memory_session_factory, score=40)
    document_path = tmp_path / "case.txt"
    _write_case_document(document_path)
    workflow_id = str(uuid4())

    first_pause = await workflow.start({"workflow_id": workflow_id, "document_path": str(document_path)})
    assert first_pause.status == "PAUSED"

    second_pause = await workflow.resume(
        workflow_id,
        decision="REQUEST_MORE_INFO",
        notes="Need one clarification",
    )
    assert second_pause.status == "PAUSED"
    assert second_pause.risk_score == 40
    assert second_pause.risk_reasoning is not None
    snapshot = workflow.build_graph().get_state({"configurable": {"thread_id": workflow_id}})
    assert snapshot.next == ("decision_agent",)

    final_result = await workflow.resume(workflow_id, decision="APPROVED", notes="Clarification resolved")
    assert final_result.status == "COMPLETED"
    assert final_result.human_decision == "APPROVED"
    assert final_result.risk_score == 40


@pytest.mark.asyncio
async def test_human_review_audit_payload_excludes_raw_document_text(
    tmp_path: Path,
    in_memory_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Human-review audit payload must exclude full_text and raw document strings."""
    workflow, audit_logger = _build_workflow(tmp_path, in_memory_session_factory, score=35)
    document_path = tmp_path / "case.txt"
    _write_case_document(document_path)
    workflow_id = str(uuid4())

    await workflow.start({"workflow_id": workflow_id, "document_path": str(document_path)})
    trail = await audit_logger.get_trail(workflow_id)
    human_review_events = [event for event in trail if event["stage"] == "human_review"]
    assert human_review_events

    for event in human_review_events:
        payload = json.dumps(event["event_data"]).lower()
        assert "full_text" not in payload
        assert "meridian supplies ltd" not in payload
        assert "completed and signed by cfo" not in payload


def test_load_and_validate_rules_rejects_malformed_schema(tmp_path: Path) -> None:
    """Malformed rules.json fails with clear RuleEngineError."""
    workflows_root = tmp_path / "workflows"
    rules_dir = workflows_root / "compliance_review"
    rules_dir.mkdir(parents=True)
    rules_dir.joinpath("rules.json").write_text(
        json.dumps(
            [
                {
                    "id": "BROKEN-1",
                    "name": "Missing operator and severity",
                    "description": "invalid schema",
                    "field": "country",
                    "value": "IN",
                }
            ]
        ),
        encoding="utf-8",
    )

    engine = RuleEngine(workflows_root=str(workflows_root))
    with pytest.raises(RuleEngineError, match="missing 'operator'"):
        load_and_validate_rules(engine)
