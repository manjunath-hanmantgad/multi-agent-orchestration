# Azure Deployment Path (Env-Only Changes)

This guide keeps application code unchanged and moves infrastructure/config to Azure.

## 1) Provision Azure Services

1. Azure Container Apps (runtime for `uvicorn app.main:app`)
2. Azure Database for PostgreSQL Flexible Server
3. Azure Blob Storage account + container for report/document artifacts
4. Azure Key Vault for secrets
5. (Optional) Azure Monitor + Log Analytics for operational telemetry

## 2) Update Environment Variables

Use these runtime variables in Container Apps configuration:

```bash
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-4-6
ANTHROPIC_API_KEY=@Microsoft.KeyVault(SecretUri=https://meridian-kv.vault.azure.net/secrets/anthropic-api-key/)
OPENAI_API_KEY=@Microsoft.KeyVault(SecretUri=https://meridian-kv.vault.azure.net/secrets/openai-api-key/)

DATABASE_URL=<postgresql+asyncpg connection string — retrieve from Azure Key Vault>

SLACK_WEBHOOK_URL=<Slack webhook URL — retrieve from Azure Key Vault>
SECRET_KEY=@Microsoft.KeyVault(SecretUri=https://meridian-kv.vault.azure.net/secrets/app-secret-key/)
DEBUG=false
```

Notes:
- Keep variable names identical to local. Only values change.
- `DATABASE_URL` is the critical switch from SQLite to PostgreSQL.

## 3) Database Initialization

Run schema setup against Azure PostgreSQL before first traffic:

```bash
python scripts/init_db.py
```

If you keep `scripts/init_db.py` SQLite-only for local use, initialize Postgres with your migration workflow and then start the app with the same table schema used by `core/schemas.py`.

## 4) Artifact Storage

For production, route generated reports and uploaded docs to Blob Storage instead of local `outputs/`.

Minimum path:
1. Add Blob container credentials via Key Vault.
2. Replace local file writes in report/document flows with Blob client writes.
3. Keep output object keys deterministic (`workflow_id/...`) to preserve audit traceability.

## 5) Deploy Container

1. Build image with project root as context.
2. Set startup command to:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
3. Expose port `8000` in Container Apps ingress.
4. Attach all env vars from step 2.

## 6) Post-Deployment Verification

1. `GET /api/health` returns `{"success": true, ...}`
2. Start a workflow via `POST /api/workflows/start`
3. Confirm pause/resume path works through `/api/workflows/{id}/decide`
4. Confirm audit trail retrieval via `/api/workflows/{id}/audit`
5. Confirm dashboard, review, and audit pages render correctly
