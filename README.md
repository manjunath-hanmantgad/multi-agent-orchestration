# Enterprise Agentic Workflow Platform

Production-style multi-agent workflow system for regulated enterprise operations.

## What This Project Does

- Runs pluggable business workflows (Compliance Review and Procurement) on LangGraph with persisted state.
- Supports real human-in-the-loop decisions by pausing workflows and resuming from checkpoints.
- Produces immutable audit trails and structured outputs for traceability and governance.

## Architecture Reference

- System architecture and state-machine details: [docs/architecture.md](docs/architecture.md)

## Local Quickstart (5 Commands)

```bash
git clone https://github.com/manjunath-hanmantgad/LLM-Production-Monitoring.git
cd LLM-Production-Monitoring/multi-agent-workflow && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env && python scripts/init_db.py
python scripts/seed_demo.py
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

After startup:
- Dashboard: `http://127.0.0.1:8000/dashboard`
- Review page (seeded paused run): `http://127.0.0.1:8000/review/00000000-0000-0000-0000-000000000202`
- API health: `http://127.0.0.1:8000/api/health`

## Demo Walkthrough (5 Minutes)

1. Open `/dashboard` and show the three seeded runs: `APPROVED`, `PAUSED`, and `REJECTED`.
2. Open the paused run review page and show extracted fields, rule summary, risk score, and decision actions.
3. Submit a decision from the review screen and show the workflow state transition.
4. Open the audit page for the same workflow and show the ordered event timeline with actor/stage context.
5. Open `/api/health` and one workflow API endpoint to show API envelope consistency (`{success, data, error}`).

## Azure Production Path

Move from local development to Azure by switching infrastructure behind the same code paths:

| Local Component | Azure Production Equivalent |
|---|---|
| SQLite (`DATABASE_URL=sqlite+aiosqlite:///...`) | Azure Database for PostgreSQL (`DATABASE_URL=postgresql+asyncpg://...`) |
| Anthropic/OpenAI direct key in `.env` | Azure Key Vault + Managed Identity secret retrieval |
| Local file outputs (`outputs/`) | Azure Blob Storage container |
| Local `uvicorn` process | Azure Container Apps deployment |

Deployment-specific environment and rollout steps: [docs/deployment.md](docs/deployment.md)

## Tech Stack

| Layer | Technology |
|---|---|
| Workflow orchestration | LangGraph (StateGraph + checkpoint + interrupt/resume) |
| API gateway | FastAPI + Uvicorn |
| Data persistence | SQLAlchemy async + SQLite (Postgres-ready) |
| LLM abstraction | LangChain Anthropic / LangChain OpenAI |
| Document parsing | pdfplumber, python-docx |
| UI rendering | Jinja2 templates + Tailwind CSS |
| Testing | pytest, pytest-asyncio, httpx |
