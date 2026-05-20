# Demo Script — Multi-Agent Workflow

**Duration:** 15–20 minutes  
**Audience:** Enterprise automation, compliance, and architecture stakeholders  
**What you need open:** `http://localhost:8020/dashboard`, `http://localhost:8010/docs`, terminal

## Pre-demo setup (do this 10 minutes before)
- [ ] Start stack: `docker compose up --build` (or `make up`)
- [ ] Seed demo data: `python scripts/seed_demo.py`
- [ ] Verify API: `curl http://localhost:8010/api/health`
- [ ] Open dashboard: `http://localhost:8020/dashboard`

## The problem you're solving (2 minutes)
> Say: "Workflow automation often loses traceability across AI and human handoffs. This platform persists state across pauses and records every decision as a verifiable audit trail."

## The solution overview (3 minutes)
> Show `docs/architecture.md` and describe: workflow registry, state manager/checkpointer, human escalation manager, and audit logger.

## Live demo walkthrough (10 minutes)

### Step 1 — Show existing runs
Open `/dashboard`.

Expected output: runs across states such as `APPROVED`, `PAUSED`, and `REJECTED`.

### Step 2 — Open a paused review
Open `/review/{workflow_id}` for a paused run.

Expected output: extracted fields, rule outcomes, risk context, and decision controls.

### Step 3 — Submit a decision
Submit `APPROVED` (or `REQUEST_MORE_INFO`) via UI/API.

Expected output: workflow status updates and progression to the next stage.

### Step 4 — Show immutable audit trail
Open `/audit/{workflow_id}`.

Expected output: ordered SYSTEM/HUMAN events with timestamps and payload details.

### Step 5 — API proof points
Call:
- `GET /api/workflows`
- `GET /api/workflows/pending`
- `GET /api/workflows/{workflow_id}`

Expected output: consistent status and checkpoint metadata.

## Business value close (2 minutes)
> Say: "The platform gives governed automation: resumable workflows, deterministic human checkpoints, and regulator-ready audit evidence."

## Fallback plan
If live stack is unstable:
- Use screenshots in `demo/`.
- Walk through `README.md` sequence diagrams and state machine.
- Show seeded run payloads from DB/API responses.

## Common demo gotchas
- API and UI ports swapped (`8010` API, `8020` UI in Docker Compose).
- Missing `CHECKPOINT_DB_URL` for environments with restricted write paths.
- Not seeding demo runs before opening dashboard.
