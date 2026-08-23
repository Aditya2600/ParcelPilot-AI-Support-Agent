.PHONY: up down logs test eval

# Full stack (API + Postgres/ParadeDB), built and started in the background.
up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f

# Deterministic suite only -- live_llm cases hit the real Medha endpoint and are
# excluded here on purpose. Runs on the host venv against the compose db
# (published on localhost:5434), not inside the api container.
test:
	.venv/bin/pytest -m "not live_llm"

# Live 28-case evaluation benchmark against the real Medha endpoint. Requires
# `make up` (or an equivalent db) and a reachable MEDHA_BASE_URL.
eval:
	.venv/bin/python scripts/run_eval.py
