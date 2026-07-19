.PHONY: up down migrate api web lint test

up:
	docker compose up -d

down:
	docker compose down

migrate:
	cd backend && uv run alembic upgrade head

api:
	cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

web:
	cd frontend && pnpm dev

lint:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app
	cd frontend && pnpm lint

test:
	cd backend && uv run pytest tests/ -v
	cd frontend && pnpm test

format:
	cd backend && uv run ruff format . && uv run ruff check --fix .
