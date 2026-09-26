# RecallGraph

**Search authoritative U.S. government safety data to find out whether a product you own, or
are considering buying, has an official recall or documented safety issue.**

> Status: early development (Step 6 of 32). Only the items under **Implemented** exist today.

## Core principles

- **Official data establishes recall truth.** Recall status comes only from ingested government
  records with preserved provenance, never from an LLM.
- **"No matching recall found" is not "safe."** It means no match exists in the datasets
  RecallGraph has ingested.
- **Every metric is reproducible.** Numbers in this repository come from commands recorded under
  [`evidence/`](evidence/).

## Implemented

- FastAPI backend with an application factory and a versioned API (`/api/v1`)
- `GET /api/v1/health` liveness endpoint
- Environment-driven configuration (pydantic-settings, `RECALLGRAPH_*` variables)
- Structured JSON logging (structlog) with per-request correlation IDs (`X-Request-ID`)
- RFC 9457 problem-details error responses (`application/problem+json`) that do not leak
  internal errors or echo rejected input
- Tests with pytest + HTTPX; ruff linting/formatting; mypy in strict mode
- GitHub Actions CI running lint, type checks and tests from the locked dependency set
- PostgreSQL 17 (Docker Compose), async SQLAlchemy 2.x, Alembic migrations, `GET /api/v1/ready`
  readiness probe (503 problem details when the database is unreachable)
- Provenance data model: sources, ingestion runs and versioned raw records with SHA-256 content
  hashes and idempotent storage (tested against real PostgreSQL)

## Planned

See [`docs/ROADMAP.md`](docs/ROADMAP.md). Highlights, **none of which are implemented yet**:
CPSC and NHTSA ingestion, normalized recall model,
search, explainable matching with a labeled evaluation set, authentication, saved inventory,
Recall Radar notifications, evidence-grounded AI explanations, Next.js frontend, security
hardening, observability, benchmarks, and AWS deployment.

## Local development

Requirements: macOS/Linux, [uv](https://docs.astral.sh/uv/), GNU make.

```bash
make install   # create .venv from uv.lock (Python 3.12, uv-managed)
make check     # ruff + mypy --strict + pytest
make run       # API on http://127.0.0.1:8001  (docs at /docs)
```

## Repository layout

```
backend/          FastAPI service (src/recallgraph, tests)
docs/             ROADMAP.md, DECISIONS.md
evidence/         verified command outputs only
.github/workflows CI
```
