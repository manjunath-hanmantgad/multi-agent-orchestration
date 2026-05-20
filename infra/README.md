# Infrastructure — Multi-Agent Workflow

## Deploy (dev)

```bash
az group create --name maw-dev-rg --location eastus

az deployment group create \
  --resource-group maw-dev-rg \
  --template-file infra/bicep/main.bicep \
  --parameters infra/environments/dev.parameters.json \
  --parameters postgresAdminPassword="$(openssl rand -base64 24)"
```

## Required Python change before Azure deployment

The LangGraph checkpointer must be switched from SQLite to PostgreSQL.

Current `requirements.txt`:
  langgraph-checkpoint-sqlite==2.0.11

Change to:
  langgraph-checkpoint-postgres>=2.0.0

In `core/database.py` or wherever the checkpointer is initialized:

  # Before:
  from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
  checkpointer = AsyncSqliteSaver.from_conn_string("checkpoints.db")

  # After (production):
  from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
  checkpointer = AsyncPostgresSaver.from_conn_string(os.environ["DATABASE_URL"])

This change is NOT made by T11. It is a separate task that must be done before
`az deployment group create` can run against a real Azure environment.

## LangGraph checkpoint table initialization
After deploying PostgreSQL, run:
  python -c "from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver; ..."
to create the LangGraph checkpoint tables. Details in LangGraph docs.
