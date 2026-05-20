# Azure Deployment Guide — Multi-Agent Workflow

## Prerequisites
- Azure CLI 2.50+
- Bicep CLI (`az bicep install`)
- Docker
- Contributor access to target resource group
- Secrets for LLM provider, database, and app secret key

## First-time deployment

### Step 1 — Create resource group
```bash
az login
az group create \
  --name maw-dev-rg \
  --location eastus
```

### Step 2 — Deploy infrastructure
```bash
az deployment group create \
  --resource-group maw-dev-rg \
  --template-file infra/bicep/main.bicep \
  --parameters infra/environments/dev.parameters.json \
  --parameters postgresAdminPassword="$(openssl rand -base64 24)"
```

Capture outputs for ACR, Container Apps, and Key Vault.

### Step 3 — Build and push image
```bash
az acr login --name <ACR_NAME>

docker build -t <ACR_LOGIN_SERVER>/multi-agent-workflow:latest .
docker push <ACR_LOGIN_SERVER>/multi-agent-workflow:latest
```

### Step 4 — Add secrets to Key Vault
```bash
az keyvault secret set \
  --vault-name <KEY_VAULT_NAME> \
  --name maw-llm-api-key \
  --value "$OPENAI_API_KEY"

az keyvault secret set \
  --vault-name <KEY_VAULT_NAME> \
  --name maw-secret-key \
  --value "$(openssl rand -base64 32)"

az keyvault secret set \
  --vault-name <KEY_VAULT_NAME> \
  --name maw-database-url \
  --value "postgresql+asyncpg://<user>:<password>@<host>:5432/workflow_platform"
```

### Step 5 — Configure Container App environment variables
```bash
az containerapp update \
  --name <MAW_API_CONTAINER_APP> \
  --resource-group maw-dev-rg \
  --set-env-vars \
    LLM_PROVIDER=openai \
    OPENAI_API_KEY=<from-key-vault> \
    DATABASE_URL="postgresql+asyncpg://<user>:<password>@<host>:5432/workflow_platform" \
    CHECKPOINT_DB_URL="postgresql+asyncpg://<user>:<password>@<host>:5432/workflow_platform" \
    SECRET_KEY=<from-key-vault>
```

### Step 6 — Verify
```bash
curl https://<MAW_API_FQDN>/health
curl https://<MAW_API_FQDN>/api/health
```
Expected both endpoints to return success.

## Ongoing deployments
- Push updated image to ACR.
- Update API and UI Container App revisions.
- Validate `/api/health`, workflow start, and decision submission flow.

## Rollback
Follow revision rollback steps in `RUNBOOK.md`.
