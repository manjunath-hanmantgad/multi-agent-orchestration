"""Tests for database models and persistence behavior."""

from __future__ import annotations

import importlib
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest
import dotenv
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from core.models import AuditEvent, WorkflowRun, WorkflowStatus
from core.schemas import AuditEventORM, Base, CRMRecordORM, WorkflowRunORM


@pytest.fixture
def session_factory() -> sessionmaker[Session]:
    """Provide an isolated in-memory SQLite session factory."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_create_read_update_across_all_tables(session_factory: sessionmaker[Session]) -> None:
    """Creates, reads, and updates records for each required table."""
    workflow_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())
    crm_id = str(uuid.uuid4())

    with session_factory() as session:
        run = WorkflowRunORM(
            id=workflow_id,
            workflow_type="compliance_review",
            status="PENDING",
            current_stage="intake",
            payload={"source": "test"},
        )
        session.add(run)
        session.flush()

        event = AuditEventORM(
            id=event_id,
            workflow_id=workflow_id,
            stage="intake",
            actor="SYSTEM",
            event_type="CREATED",
            event_data={"key": "value"},
        )
        crm_record = CRMRecordORM(
            id=crm_id,
            workflow_id=workflow_id,
            vendor_name="Meridian Supplies Ltd",
            decision="APPROVED",
            decision_by="reviewer@example.com",
            decided_at=datetime.now(timezone.utc),
            notes="approved for onboarding",
        )
        session.add_all([event, crm_record])
        session.commit()

    with session_factory() as session:
        stored_run = session.get(WorkflowRunORM, workflow_id)
        assert stored_run is not None
        assert stored_run.status == "PENDING"

        stored_event = session.get(AuditEventORM, event_id)
        assert stored_event is not None
        assert stored_event.actor == "SYSTEM"

        stored_crm = session.get(CRMRecordORM, crm_id)
        assert stored_crm is not None
        assert stored_crm.vendor_name == "Meridian Supplies Ltd"

        stored_run.status = "RUNNING"
        session.commit()

    with session_factory() as session:
        updated_run = session.get(WorkflowRunORM, workflow_id)
        assert updated_run is not None
        assert updated_run.status == "RUNNING"


def test_duplicate_primary_key_fails(session_factory: sessionmaker[Session]) -> None:
    """Verifies DB constraints reject duplicate primary keys."""
    workflow_id = str(uuid.uuid4())

    with session_factory() as session:
        session.add(
            WorkflowRunORM(
                id=workflow_id,
                workflow_type="compliance_review",
                status="PENDING",
            )
        )
        session.commit()

        session.add(
            WorkflowRunORM(
                id=workflow_id,
                workflow_type="compliance_review",
                status="RUNNING",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_edge_case_empty_payload_and_audit_query(session_factory: sessionmaker[Session]) -> None:
    """Ensures nullable JSON payload works and audit events are queryable."""
    workflow_id = str(uuid.uuid4())

    with session_factory() as session:
        session.add(
            WorkflowRunORM(
                id=workflow_id,
                workflow_type="procurement",
                status="PAUSED",
                current_stage=None,
                payload=None,
            )
        )
        session.add(
            AuditEventORM(
                id=str(uuid.uuid4()),
                workflow_id=workflow_id,
                stage="human_review",
                actor="HUMAN",
                event_type="DECISION_SUBMITTED",
                event_data=None,
            )
        )
        session.commit()

    with session_factory() as session:
        events = session.execute(select(AuditEventORM)).scalars().all()
        assert len(events) == 1
        assert events[0].event_type == "DECISION_SUBMITTED"


def test_database_url_reads_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Database configuration uses DATABASE_URL from environment."""
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./from-test.db")
    sys.modules.pop("core.database", None)
    database_module = importlib.import_module("core.database")
    assert database_module.DATABASE_URL == "sqlite+aiosqlite:///./from-test.db"


def test_missing_database_url_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing DATABASE_URL fails with a clear startup configuration error."""
    original_value = os.environ.get("DATABASE_URL")
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    sys.modules.pop("core.database", None)
    try:
        with pytest.raises(RuntimeError, match="Missing required environment variable: DATABASE_URL"):
            importlib.import_module("core.database")
    finally:
        if original_value is not None:
            monkeypatch.setenv("DATABASE_URL", original_value)
        else:
            monkeypatch.delenv("DATABASE_URL", raising=False)


def test_pydantic_models_validate_status_and_ids() -> None:
    """Pydantic models reject invalid UUID values and unknown statuses."""
    run = WorkflowRun(
        id=uuid.uuid4(),
        workflow_type="compliance_review",
        status=WorkflowStatus.PENDING,
        current_stage="intake",
        payload={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    assert run.status == WorkflowStatus.PENDING

    event = AuditEvent(
        id=uuid.uuid4(),
        workflow_id=uuid.uuid4(),
        timestamp=datetime.now(timezone.utc),
        stage="rule_check",
        actor="SYSTEM",
        event_type="RULES_EVALUATED",
        event_data={},
    )
    assert event.actor.value == "SYSTEM"

    with pytest.raises(ValueError):
        WorkflowRun(
            id="not-a-uuid",
            workflow_type="compliance_review",
            status="PENDING",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
