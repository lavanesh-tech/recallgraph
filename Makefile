BACKEND := backend
API_PORT ?= 8001
FROM_YEAR ?= 1970

.PHONY: install db-up db-down migrate migrate-check lint format typecheck test test-unit check run ingest-cpsc stats

install:
	cd $(BACKEND) && uv sync
db-up:
	docker compose up -d --wait postgres
db-down:
	docker compose down
migrate:
	cd $(BACKEND) && uv run alembic upgrade head
lint:
	cd $(BACKEND) && uv run ruff check . && uv run ruff format --check .
format:
	cd $(BACKEND) && uv run ruff check --fix . && uv run ruff format .
typecheck:
	cd $(BACKEND) && uv run mypy src tests
test:
	cd $(BACKEND) && uv run pytest
test-unit:
	cd $(BACKEND) && uv run pytest -m "not integration"
check: lint typecheck test
run:
	cd $(BACKEND) && uv run uvicorn recallgraph.main:create_app --factory --host 127.0.0.1 --port $(API_PORT) --reload --no-access-log
migrate-check:
	cd $(BACKEND) && uv run alembic check
ingest-cpsc:
	cd $(BACKEND) && uv run recallgraph ingest cpsc --from-year $(FROM_YEAR)
stats:
	cd $(BACKEND) && uv run recallgraph stats
