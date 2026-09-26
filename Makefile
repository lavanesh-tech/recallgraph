BACKEND := backend
API_PORT ?= 8001

.PHONY: install lint format typecheck test check run

install:
	cd $(BACKEND) && uv sync
lint:
	cd $(BACKEND) && uv run ruff check . && uv run ruff format --check .
format:
	cd $(BACKEND) && uv run ruff check --fix . && uv run ruff format .
typecheck:
	cd $(BACKEND) && uv run mypy src tests
test:
	cd $(BACKEND) && uv run pytest
check: lint typecheck test
run:
	cd $(BACKEND) && uv run uvicorn recallgraph.main:create_app --factory --host 127.0.0.1 --port $(API_PORT) --reload --no-access-log
