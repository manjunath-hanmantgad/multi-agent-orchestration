"""Demo UI server for dashboard, review, and audit pages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from api.main import create_app as create_api_app
from core.audit import AuditLogger
from core.database import AsyncSessionLocal
from core.registry import registry
from core.schemas import WorkflowRunORM

APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
audit_logger = AuditLogger()
app = create_api_app()
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

STATUS_BADGES = {
    "APPROVED": "status-approved",
    "REJECTED": "status-rejected",
    "PAUSED": "status-paused",
    "RUNNING": "status-running",
    "PENDING": "status-pending",
    "COMPLETED": "status-approved",
    "FAILED": "status-rejected",
}


@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard", status_code=302)


@app.get("/dashboard")
async def dashboard(request: Request) -> Any:
    runs = await _list_runs()
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "runs": runs, "page_title": "Dashboard"},
    )


@app.get("/review/{workflow_id}")
async def review(request: Request, workflow_id: str) -> Any:
    run = await _get_run(workflow_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    context = _review_context(run)
    return templates.TemplateResponse(
        "review.html",
        {"request": request, "context": context, "page_title": "Review"},
    )


@app.get("/audit/{workflow_id}")
async def audit_page(request: Request, workflow_id: str) -> Any:
    run = await _get_run(workflow_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    events = await audit_logger.get_trail(workflow_id)
    timeline = [_timeline_item(event) for event in events]
    return templates.TemplateResponse(
        "audit.html",
        {
            "request": request,
            "workflow": _serialize_run(run),
            "timeline": timeline,
            "page_title": "Audit",
        },
    )


@app.get("/demo/start")
async def start_demo() -> RedirectResponse:
    try:
        workflow = registry.get("procurement")
        payload = _demo_payload()
        result = await workflow.start(payload)
        workflow_id = (
            result.workflow_id if hasattr(result, "workflow_id") else payload.get("workflow_id", "")
        )
        if workflow_id:
            return RedirectResponse(url=f"/review/{workflow_id}", status_code=302)
    except (LookupError, RuntimeError, ValueError, TypeError):
        pass
    return RedirectResponse(url="/dashboard", status_code=302)


async def _list_runs() -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WorkflowRunORM).order_by(WorkflowRunORM.created_at.desc())
        )
        rows = result.scalars().all()
    return [_serialize_run(row) for row in rows]


async def _get_run(workflow_id: str) -> WorkflowRunORM | None:
    async with AsyncSessionLocal() as session:
        return await session.get(WorkflowRunORM, workflow_id)


def _serialize_run(row: WorkflowRunORM) -> dict[str, Any]:
    return {
        "id": row.id,
        "id_short": row.id[:8],
        "workflow_type": row.workflow_type,
        "status": row.status,
        "status_class": STATUS_BADGES.get(row.status, "status-pending"),
        "current_stage": row.current_stage or "-",
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
        "payload": row.payload or {},
    }


def _review_context(run: WorkflowRunORM) -> dict[str, Any]:
    data = _serialize_run(run)
    checkpoint = _checkpoint_state(run)
    extracted = checkpoint.get("extracted_data", {})
    rule_results = checkpoint.get("rule_results", {})
    extracted_summary = _extracted_summary(extracted)
    rule_summary = _rule_summary(rule_results)
    rule_rows = _rule_rows(rule_results)
    return {
        "workflow_id": data["id"],
        "workflow_type": data["workflow_type"],
        "status": data["status"],
        "status_class": data["status_class"],
        "current_stage": data["current_stage"],
        "extracted_summary": extracted_summary,
        "rule_summary": rule_summary,
        "rule_rows": rule_rows,
        "risk_score": checkpoint.get("risk_score", "-"),
        "risk_reasoning": checkpoint.get("risk_reasoning", checkpoint.get("risk_summary", "Not available")),
    }


def _checkpoint_state(run: WorkflowRunORM) -> dict[str, Any]:
    payload = run.payload if isinstance(run.payload, dict) else {}
    checkpoint = payload.get("checkpoint_data", {})
    state = checkpoint.get("state", {})
    return state if isinstance(state, dict) else {}


def _extracted_summary(extracted: Any) -> list[dict[str, str]]:
    summary: list[dict[str, str]] = []
    if isinstance(extracted, dict):
        metadata = extracted.get("metadata", {})
        if isinstance(metadata, dict):
            summary.append({"label": "Document Type", "value": str(metadata.get("file_type", "-"))})
            summary.append({"label": "Page Count", "value": str(metadata.get("page_count", "-"))})
        fields = extracted.get("structured_fields", {})
        if isinstance(fields, dict):
            summary.append({"label": "Field Count", "value": str(len(fields))})
            keys = ", ".join(sorted(k.replace("_", " ").title() for k in fields.keys() if k != "full_text"))
            summary.append({"label": "Fields", "value": keys or "-"})
    if not summary:
        summary.append({"label": "Summary", "value": "No extracted context available."})
    return summary


def _rule_summary(rule_results: Any) -> list[dict[str, str]]:
    if not isinstance(rule_results, dict):
        return [{"label": "Rules", "value": "No rule results available."}]
    return [
        {"label": "Passed", "value": str(len(rule_results.get("passed", [])))},
        {"label": "Failed", "value": str(len(rule_results.get("failed", [])))},
        {"label": "Flagged", "value": str(len(rule_results.get("flagged", [])))},
    ]


def _rule_rows(rule_results: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not isinstance(rule_results, dict):
        return rows
    for bucket, items in rule_results.items():
        if not isinstance(items, list):
            continue
        for rule in items:
            if not isinstance(rule, dict):
                continue
            rows.append(
                {
                    "name": str(rule.get("name", "Unnamed Rule")),
                    "severity": str(rule.get("severity", "-")).upper(),
                    "status": bucket.upper(),
                    "field": str(rule.get("field", "-")),
                }
            )
    return rows


def _timeline_item(event: dict[str, Any]) -> dict[str, Any]:
    event_data = event.get("event_data", {})
    pairs = _flatten_pairs(event_data if isinstance(event_data, dict) else {})
    return {
        "timestamp": event.get("timestamp", ""),
        "stage": event.get("stage", "-"),
        "actor": event.get("actor", "-"),
        "event_type": event.get("event_type", "-"),
        "pairs": pairs,
        "actor_class": "actor-human" if event.get("actor") == "HUMAN" else "actor-system",
    }


def _flatten_pairs(data: dict[str, Any], prefix: str = "") -> list[dict[str, str]]:
    pairs: list[dict[str, str]] = []
    for key, value in data.items():
        name = f"{prefix} {key}".strip()
        if isinstance(value, dict):
            pairs.extend(_flatten_pairs(value, name))
        elif isinstance(value, list):
            rendered = ", ".join(str(item) for item in value)
            pairs.append({"key": name, "value": rendered or "-"})
        else:
            pairs.append({"key": name, "value": str(value)})
    return pairs


def _demo_payload() -> dict[str, Any]:
    demo_file = APP_DIR / "mock_data" / "procurement_case.json"
    if demo_file.exists():
        try:
            data = json.loads(demo_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "vendor_data": {
            "vendor_name": "Atlas Components Pvt Ltd",
            "kyc_complete": True,
            "tax_id": "TAX-440001",
            "annual_revenue": 3500000,
            "years_in_business": 6,
        }
    }
