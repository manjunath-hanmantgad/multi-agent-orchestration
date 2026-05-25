# Codebase Map — Multi-Agent Orchestration Platform

| Path | Purpose | Key files |
|---|---|---|
| `core/` | Shared business logic — database, models, state, schemas, audit, LLM client, metrics, registry | `database.py`, `models.py`, `state.py`, `schemas.py`, `audit.py`, `llm_client.py`, `registry.py`, `tool_registry.py` |
| `core/services/` | Domain services — document parsing, rule engine, notification, report generation | `document_parser.py`, `rule_engine.py`, `notification.py`, `report_generator.py` |
| `workflows/` | Pluggable LangGraph workflow definitions — one sub-package per workflow type | — |
| `workflows/procurement/` | Procurement approval workflow — agents, state schema, LangGraph graph | `workflow.py`, `agents.py`, `schema.py` |
| `workflows/compliance_review/` | Compliance review workflow — agents, rules, state schema, LangGraph graph | `workflow.py`, `agents.py`, `schema.py`, `rules.json` |
| `api/` | FastAPI layer — routers for workflows, approvals, audit | `main.py`, `dependencies.py`, `routers/workflows.py`, `routers/approvals.py`, `routers/audit.py` |
| `app/` | Web UI — FastAPI+Jinja2 server, HTML templates, static assets | `main.py`, `templates/dashboard.html`, `templates/review.html`, `templates/audit.html` |
| `app/mock_data/` | Sample case payloads for demo | `procurement_case.json`, `compliance_case.json` |
| `mcp-server/` | MCP server exposing workflow tools to Claude Code | `server.py`, `client.py`, `tools/start_workflow.py`, `tools/submit_decision.py`, `tools/get_status.py`, `tools/get_audit_trail.py` |
| `scripts/` | DB init, demo seed, screenshot capture | `init_db.py`, `seed_demo.py`, `take_screenshots.py` |
| `evals/` | Golden evaluation dataset and scoring runner | `golden_dataset.json`, `run_evals.py`, `report.md` |
| `demo/` | Demo screenshots | `dashboard.png`, `review-screen.png`, `audit-trail.png` |
| `infra/` | Azure Bicep IaC | `bicep/main.bicep`, `environments/` |
| `docs/` | Technical documentation — architecture, deployment, blog posts | `architecture.md`, `deployment.md` |
| `tests/` | pytest test suite | `test_api.py`, `test_procurement_workflow.py`, `test_compliance_workflow.py`, `test_audit.py`, `test_mcp_tools.py` |
| `Makefile` | Dev commands | — |
| `requirements.txt` | Python dependencies | — |
