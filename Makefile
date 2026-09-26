BACKEND := backend
API_PORT ?= 8001
FROM_YEAR ?= 1970

.PHONY: install db-up db-down migrate migrate-check lint format typecheck test test-unit check run ingest-cpsc stats normalize-cpsc ingest-nhtsa normalize-nhtsa radar-run radar-cycle mail-up worker

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
normalize-cpsc:
	cd $(BACKEND) && uv run recallgraph normalize cpsc
ingest-nhtsa:
	cd $(BACKEND) && uv run recallgraph ingest nhtsa
normalize-nhtsa:
	cd $(BACKEND) && uv run recallgraph normalize nhtsa
radar-run:
	cd $(BACKEND) && uv run recallgraph radar run
radar-cycle:
	cd $(BACKEND) && uv run recallgraph radar cycle
mail-up:
	docker compose up -d mailpit
worker:
	cd $(BACKEND) && uv run recallgraph worker run

.PHONY: web-install web-dev web-check
web-install:
	cd frontend && npm ci
web-dev:
	cd frontend && npm run dev
web-check:
	cd frontend && npm run lint && npm test && npm run build

.PHONY: coverage e2e
coverage:
	cd backend && uv run pytest -q --cov=recallgraph --cov-report=term --cov-report=json:coverage.json
	cd frontend && npm run coverage
e2e:
	cd frontend && npm run e2e

.PHONY: stack-up stack-down
stack-up:
	docker compose -f compose.stack.yml up -d --build --wait
stack-down:
	docker compose -f compose.stack.yml down
