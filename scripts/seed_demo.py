"""Seed the database with deterministic demo workflows and audit trails."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from sqlalchemy import delete

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.database import AsyncSessionLocal, create_tables
from core.audit import AuditLogger
from core.escalation import HumanEscalationManager
from core.schemas import AuditEventORM, CRMRecordORM, WorkflowRunORM
from core.state import StateManager
from workflows.compliance_review.agents import ComplianceReviewAgents
from workflows.compliance_review.workflow import ComplianceReviewWorkflow

APPROVED_ID = "00000000-0000-0000-0000-000000000101"
PAUSED_ID = "00000000-0000-0000-0000-000000000202"
REJECTED_ID = "00000000-0000-0000-0000-000000000303"
DEFAULT_CHECKPOINT_DB_URL = "./checkpoints.db"


async def seed_demo() -> None:
    """Create idempotent demo workflows for dashboard and review pages."""
    load_dotenv()
    _reset_checkpoint_store()
    await create_tables()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    async with AsyncSessionLocal() as session:
        await _clear_existing(session, [APPROVED_ID, PAUSED_ID, REJECTED_ID])
        session.add_all(_workflow_rows(now))
        session.add_all(_audit_rows(now))
        session.add(_crm_row(now))
        await session.commit()
    await _seed_paused_via_langgraph()


async def _clear_existing(session: object, workflow_ids: list[str]) -> None:
    await session.execute(delete(AuditEventORM).where(AuditEventORM.workflow_id.in_(workflow_ids)))
    await session.execute(delete(CRMRecordORM).where(CRMRecordORM.workflow_id.in_(workflow_ids)))
    await session.execute(delete(WorkflowRunORM).where(WorkflowRunORM.id.in_(workflow_ids)))


def _workflow_rows(now: datetime) -> list[WorkflowRunORM]:
    return [
        WorkflowRunORM(
            id=APPROVED_ID,
            workflow_type="compliance_review",
            status="APPROVED",
            current_stage="certificate_agent",
            payload=_payload_for_approved(),
            created_at=now - timedelta(hours=5),
            updated_at=now - timedelta(hours=4, minutes=30),
        ),
        WorkflowRunORM(
            id=REJECTED_ID,
            workflow_type="compliance_review",
            status="REJECTED",
            current_stage="rejection_agent",
            payload=_payload_for_rejected(),
            created_at=now - timedelta(hours=1, minutes=30),
            updated_at=now - timedelta(hours=1),
        ),
    ]


def _audit_rows(now: datetime) -> list[AuditEventORM]:
    base = now - timedelta(hours=5)
    return [
        _event(APPROVED_ID, base, "intake_agent", "SYSTEM", "STAGE_COMPLETED", {"source": "demo"}),
        _event(APPROVED_ID, base + timedelta(minutes=5), "rule_check_agent", "SYSTEM", "STAGE_COMPLETED", {"passed": 5, "failed": 0}),
        _event(APPROVED_ID, base + timedelta(minutes=10), "risk_scoring_agent", "SYSTEM", "STAGE_COMPLETED", {"risk_score": 18}),
        _event(APPROVED_ID, base + timedelta(minutes=12), "human_review", "SYSTEM", "REVIEW_REQUESTED", {"context": {"document_type": "pdf", "page_count": 1, "field_keys": 6}}),
        _event(APPROVED_ID, base + timedelta(minutes=20), "decision", "HUMAN", "DECISION_SUBMITTED", {"decision": "APPROVED", "notes": "All checks passed"}),
        _event(APPROVED_ID, base + timedelta(minutes=22), "certificate_agent", "SYSTEM", "STAGE_COMPLETED", {"report_path": "outputs/demo-approved/report.json"}),
        _event(REJECTED_ID, now - timedelta(hours=1, minutes=30), "intake_agent", "SYSTEM", "STAGE_COMPLETED", {"source": "demo"}),
        _event(REJECTED_ID, now - timedelta(hours=1, minutes=25), "rule_check_agent", "SYSTEM", "STAGE_COMPLETED", {"passed": 2, "failed": 2}),
        _event(REJECTED_ID, now - timedelta(hours=1, minutes=20), "risk_scoring_agent", "SYSTEM", "STAGE_COMPLETED", {"risk_score": 83}),
        _event(REJECTED_ID, now - timedelta(hours=1, minutes=18), "human_review", "SYSTEM", "REVIEW_REQUESTED", {"context": {"document_type": "pdf", "page_count": 1, "field_keys": 6, "risk_score": 83}}),
        _event(REJECTED_ID, now - timedelta(hours=1, minutes=10), "decision", "HUMAN", "DECISION_SUBMITTED", {"decision": "REJECTED", "notes": "Missing current tax declaration evidence"}),
        _event(REJECTED_ID, now - timedelta(hours=1), "rejection_agent", "SYSTEM", "STAGE_COMPLETED", {"reason": "Missing current tax declaration evidence"}),
    ]


def _event(
    workflow_id: str,
    timestamp: datetime,
    stage: str,
    actor: str,
    event_type: str,
    event_data: dict[str, object],
) -> AuditEventORM:
    return AuditEventORM(
        id=str(uuid4()),
        workflow_id=workflow_id,
        timestamp=timestamp,
        stage=stage,
        actor=actor,
        event_type=event_type,
        event_data=event_data,
    )


def _crm_row(now: datetime) -> CRMRecordORM:
    return CRMRecordORM(
        id=str(uuid4()),
        workflow_id=APPROVED_ID,
        vendor_name="Meridian Supplies Ltd",
        decision="APPROVED",
        decision_by="HUMAN",
        decided_at=now - timedelta(hours=4, minutes=35),
        notes="Approved in demo seed data",
    )


def _payload_for_approved() -> dict[str, object]:
    state = _base_state(APPROVED_ID, 18, "Low risk profile with complete declarations.")
    state.update({"human_decision": "APPROVED", "decision_notes": "All checks passed"})
    return _checkpoint_payload("certificate_agent", "APPROVED", state)


def _payload_for_rejected() -> dict[str, object]:
    state = _base_state(REJECTED_ID, 83, "Multiple rule failures indicate material compliance gaps.")
    state.update(
        {
            "human_decision": "REJECTED",
            "decision_notes": "Missing current tax declaration evidence",
        }
    )
    return _checkpoint_payload("rejection_agent", "REJECTED", state)


def _base_state(workflow_id: str, risk_score: int, risk_reasoning: str) -> dict[str, object]:
    doc_path = "app/mock_data/sample_documents/meridian_compliance_declaration.pdf"
    return {
        "workflow_id": workflow_id,
        "document_path": doc_path,
        "status": "PAUSED",
        "extracted_data": _extracted_data(),
        "rule_results": _rule_results(risk_score >= 80),
        "risk_score": risk_score,
        "risk_reasoning": risk_reasoning,
    }


def _extracted_data() -> dict[str, object]:
    return {
        "metadata": {"file_type": "pdf", "page_count": 1, "size_bytes": 2048},
        "structured_fields": {
            "entity_name": "Meridian Supplies Ltd",
            "country": "IN",
            "annual_revenue": 4200000,
            "sanctions_clearance": "clear",
            "tax_declaration": "completed",
            "declaration_year": 2026,
        },
    }


def _rule_results(high_risk: bool) -> dict[str, list[dict[str, object]]]:
    passed = [
        {"name": "Entity Name Match", "field": "entity_name", "severity": "high"},
        {"name": "Country Eligibility", "field": "country", "severity": "high"},
    ]
    failed = [{"name": "Tax Declaration Present", "field": "tax_declaration", "severity": "critical"}]
    flagged = [{"name": "Revenue Threshold", "field": "annual_revenue", "severity": "warning"}]
    if not high_risk:
        failed = []
        flagged = [{"name": "Revenue Threshold", "field": "annual_revenue", "severity": "low"}]
        passed.append({"name": "Tax Declaration Present", "field": "tax_declaration", "severity": "critical"})
    return {"passed": passed, "failed": failed, "flagged": flagged}


def _checkpoint_payload(stage: str, status: str, state: dict[str, object]) -> dict[str, object]:
    state["current_stage"] = stage
    state["status"] = status
    return {"checkpoint_data": {"workflow_type": "compliance_review", "stage": stage, "status": status, "state": state}}


def _ensure_mock_data_files() -> None:
    base = Path("app/mock_data")
    base.mkdir(parents=True, exist_ok=True)
    if not (base / "compliance_case.json").exists():
        raise RuntimeError("Missing app/mock_data/compliance_case.json")
    if not (base / "procurement_case.json").exists():
        raise RuntimeError("Missing app/mock_data/procurement_case.json")


def _print_summary() -> None:
    print("Seeded demo workflows:")
    print(f"- APPROVED: {APPROVED_ID}")
    print(f"- PAUSED:   {PAUSED_ID}")
    print(f"- REJECTED: {REJECTED_ID}")


async def _seed_paused_via_langgraph() -> None:
    """Create the paused demo workflow through real graph execution to persist checkpoints."""
    payload = _load_compliance_case_payload()
    payload["workflow_id"] = PAUSED_ID
    state_manager = StateManager()
    audit_logger = AuditLogger()
    escalation = HumanEscalationManager(state_manager=state_manager, audit_logger=audit_logger)
    agents = ComplianceReviewAgents(
        state_manager=state_manager,
        audit_logger=audit_logger,
        escalation_manager=escalation,
        risk_scorer=_mock_risk_scorer,
    )
    async with AsyncSqliteSaver.from_conn_string(_checkpoint_db_url()) as checkpointer:
        await checkpointer.setup()
        workflow = ComplianceReviewWorkflow(
            checkpointer=checkpointer,
            agents=agents,
            state_manager=state_manager,
        )
        result = await workflow.start(payload)
        if result.status != "PAUSED":
            raise RuntimeError(f"Expected PAUSED status for seeded workflow, got: {result.status}")
        checkpoint = await state_manager.load_checkpoint(PAUSED_ID)
        if not isinstance(checkpoint, dict) or not checkpoint:
            raise RuntimeError(f"Checkpoint missing for seeded paused workflow: {PAUSED_ID}")


def _load_compliance_case_payload() -> dict[str, object]:
    """Load demo compliance payload used to generate the paused workflow."""
    case_path = Path("app/mock_data/compliance_case.json")
    data = json.loads(case_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("app/mock_data/compliance_case.json must contain a JSON object")
    return dict(data)


def _mock_risk_scorer(rule_results: dict[str, list[dict[str, object]]]) -> dict[str, object]:
    """Deterministic risk scorer used during demo seeding to avoid external LLM calls."""
    failed = len(rule_results.get("failed", []))
    flagged = len(rule_results.get("flagged", []))
    risk_score = min(95, 35 + failed * 20 + flagged * 6)
    return {
        "risk_score": risk_score,
        "risk_reasoning": (
            f"Deterministic seed scoring: failed={failed}, flagged={flagged}, "
            f"computed_risk_score={risk_score}."
        ),
    }


def _checkpoint_db_url() -> str:
    value = os.getenv("CHECKPOINT_DB_URL", DEFAULT_CHECKPOINT_DB_URL).strip()
    return value or DEFAULT_CHECKPOINT_DB_URL


def _checkpoint_db_path() -> Path:
    raw = _checkpoint_db_url()
    if raw.startswith("sqlite:///"):
        raw = raw[len("sqlite:///") :]
    return Path(raw).expanduser().resolve()


def _reset_checkpoint_store() -> None:
    path = _checkpoint_db_path()
    for candidate in (path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
        if candidate.exists():
            candidate.unlink()


if __name__ == "__main__":
    _ensure_mock_data_files()
    asyncio.run(seed_demo())
    _print_summary()
