# Runbook — Multi-Agent Workflow

## Service overview
Multi-Agent Workflow orchestrates long-running workflows with persisted checkpoints, human review pauses, and immutable audit trails. Outages affect workflow start/resume, approval decisions, and operational transparency across dashboard and APIs.

## Health checks
| Endpoint | Expected | What it means |
|---|---|---|
| `GET /health` | `200` with `{"status":"ok"}` | API process is alive |
| `GET /api/health` | `200` with `success=true` and workflow count | API wiring and registry are loaded |
| `GET /metrics` | `200` Prometheus payload | Metrics endpoint is healthy |
| `GET /dashboard` (UI app) | `200` HTML | Review UI server is healthy |

## Common failure scenarios

### Workflow stuck in PAUSED
**Symptom:** runs remain in `PAUSED` and do not progress.
**Action:**
1. List pending runs via `GET /api/workflows/pending`.
2. Submit decision: `POST /api/workflows/{workflow_id}/decide`.
3. Verify status transitions in `/api/workflows/{workflow_id}`.

### Checkpoint persistence errors
**Symptom:** startup/shutdown or run operations report checkpoint failures.
**Action:**
1. Validate `CHECKPOINT_DB_URL` and write permissions.
2. Confirm API startup logs include checkpoint saver setup.
3. Retry with a known-good local path for `CHECKPOINT_DB_URL`.

### Audit trail missing/incomplete
**Symptom:** `/api/workflows/{id}/audit` missing expected events.
**Action:**
1. Verify workflow progressed through expected stages.
2. Check API logs for `audit_*_failed` messages.
3. Confirm database connectivity and schema initialization.

### UI unavailable while API is healthy
**Symptom:** API responses are healthy but `/dashboard` fails.
**Action:**
1. Confirm UI service is running on `8020`.
2. Inspect UI logs (`uvicorn app.main:app ...`).
3. Restart UI service and re-open `/dashboard`.

## Rollback procedure
```bash
az containerapp revision list \
  --name <MAW_API_CONTAINER_APP> \
  --resource-group <RESOURCE_GROUP>

az containerapp revision activate \
  --name <MAW_API_CONTAINER_APP> \
  --resource-group <RESOURCE_GROUP> \
  --revision <PREVIOUS_REVISION_NAME>
```

## Log access
```bash
# Local API/UI logs (if running with Docker Compose)
docker compose logs -f api ui

# Azure logs for API
az containerapp logs show \
  --name <MAW_API_CONTAINER_APP> \
  --resource-group <RESOURCE_GROUP> \
  --follow
```

## Contacts / escalation
- Primary owner: [fill in]
- Secondary owner: [fill in]
- Escalation SLA: [fill in]
