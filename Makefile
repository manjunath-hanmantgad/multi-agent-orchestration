.PHONY: up down test seed migrate eval lint clean health api ui

up:
	uvicorn api.main:app --reload --host 0.0.0.0 --port 8010 &
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8020 &
	@echo "API: http://localhost:8010   UI: http://localhost:8020"

down:
	pkill -f "uvicorn api.main:app --reload --host 0.0.0.0 --port 8010" 2>/dev/null || true
	pkill -f "uvicorn app.main:app --reload --host 0.0.0.0 --port 8020" 2>/dev/null || true

test:
	pytest -q

seed:
	python scripts/seed_demo.py

migrate:
	python scripts/init_db.py

eval:
	@if [ -x .venv/bin/python ]; then .venv/bin/python evals/run_evals.py; else python3 evals/run_evals.py; fi

lint:
	ruff check . --ignore=F401,E402 2>/dev/null || echo "Lint warnings noted"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	find . -name "*.pyc" -delete 2>/dev/null

health:
	curl -s http://localhost:8010/api/health | python -m json.tool 2>/dev/null || echo "API not running - run: make up"

api:
	uvicorn api.main:app --reload --host 0.0.0.0 --port 8010

ui:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8020
