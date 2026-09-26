# PROJECT_STATE — RecallGraph

Handoff document for continuing work in a new conversation. Keep it current after every step.

## Snapshot
- **Repo path:** `~/Desktop/recallgraph` (monorepo; backend in `backend/`)
- **Current step:** 5 of 32 — Database platform (in progress)
- **Next step:** 5 — Database platform (PostgreSQL via Compose on port 5433, async SQLAlchemy 2.x,
  Alembic, readiness endpoint, integration-test DB harness)
- **Git identity:** LAVANESH <lavanesh532@gmail.com>. User runs all git commands. No AI co-authors.

## Environment
- macOS 26 (arm64), zsh, conda `(base)` active but unused by project
- uv 0.12.19; Python 3.12.14 (uv-managed); Docker 29.6.2 / Compose v5.3.1
- Ports 5432/8000 taken by another project → RecallGraph uses **5433** (DB) and **8001** (API)
- Workflow note: long terminal pastes proved unreliable; steps are delivered as downloadable
  scripts run with `bash ~/Downloads/stepN_files.sh`

## Architecture (current)
Modular monolith, FastAPI app factory `recallgraph.main:create_app`.
- `core/config.py` — `Settings` (env prefix `RECALLGRAPH_`): app_name, environment, log_level, log_json
- `core/logging_config.py` — structlog JSON logging
- `core/request_context.py` — `X-Request-ID` middleware + `request_completed` log
- `core/problems.py` — RFC 9457 handlers (HTTP, validation, unhandled)
- `api/router.py` — `/api/v1` router; `api/v1/health.py`

## Endpoints
| Method | Path | Notes |
|---|---|---|
| GET | /api/v1/health | liveness: status, service, version, environment |

## Database / migrations
None yet (Step 5).

## Tests
13 tests (pytest + HTTPX ASGITransport): config (2), health (1), problems (4), request context (6).

## Verification results (actual output)
- Step 4 (2026-09-26): GitHub Actions run 36250702446 green (lint, format, mypy, pytest). Commits 65445f5, 41d8351 pushed to github.com/lavanesh-tech/recallgraph.
- Step 3 (2026-09-26): `make check` → ruff clean, mypy strict clean (16 files), **13 passed**.
  Live server: health 200; unknown route 404 `application/problem+json` echoing `request_id`;
  JSON `request_completed` log lines.

## Key decisions
See `docs/DECISIONS.md` (D-001 … D-007).

## Known issues
None.

## Measured metrics
None yet. Only metrics with evidence under `evidence/` may be claimed.
