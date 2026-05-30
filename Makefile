.PHONY: up down restart logs shell test lint fmt migrate seed

# ── Docker (production stack) ────────────────────────────────────────────────

up:
	docker compose up --build -d

down:
	docker compose down

restart:
	docker compose restart web worker

logs:
	docker compose logs -f web worker

shell:
	docker compose exec web bash

migrate:
	docker compose exec web alembic upgrade head

# ── Local dev (no Docker needed — v1 standalone) ────────────────────────────

dev:
	python main.py

# ── Quality ──────────────────────────────────────────────────────────────────

test:
	python -m pytest tests/ -v --tb=short

lint:
	python -m ruff check engine/ app/ tests/ main.py
	python -m ruff format --check engine/ app/ tests/ main.py

fmt:
	python -m ruff format engine/ app/ tests/ main.py
	python -m ruff check --fix engine/ app/ tests/ main.py
