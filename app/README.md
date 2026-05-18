# Demo UI Run Guide

This UI exposes three pages used in the product demo:
- `GET /dashboard`
- `GET /review/{workflow_id}`
- `GET /audit/{workflow_id}`

## Run Steps

From project root:

```bash
source .venv/bin/activate
cp .env.example .env
python scripts/init_db.py
python scripts/seed_demo.py
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## Demo URLs

- Dashboard: `http://127.0.0.1:8000/dashboard`
- Paused review case: `http://127.0.0.1:8000/review/00000000-0000-0000-0000-000000000202`
- Approved audit trail: `http://127.0.0.1:8000/audit/00000000-0000-0000-0000-000000000101`
- Rejected audit trail: `http://127.0.0.1:8000/audit/00000000-0000-0000-0000-000000000303`

## Notes

- `scripts/seed_demo.py` is idempotent and can be run repeatedly.
- The review page submits decisions through the API endpoints mounted on the same FastAPI app.
