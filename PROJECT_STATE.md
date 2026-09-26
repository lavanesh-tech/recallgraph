# PROJECT_STATE — RecallGraph

Handoff document for continuing work in a new conversation. Keep it current after every step.

## Snapshot
- **Repo:** `~/Desktop/recallgraph` → https://github.com/lavanesh-tech/recallgraph (public)
- **Current step:** 7 of 32 — CPSC ingestion pipeline (in progress)
- **Next step:** 7 — CPSC ingestion pipeline (resilient HTTP client, idempotent raw storage via
  `RawRecordRepository`, CLI command, synthetic tests, one real ingestion run → `evidence/`)
- **Git identity:** LAVANESH <lavanesh532@gmail.com>. User runs all git commands. No AI co-authors.
- **Workflow:** each step is a downloadable script run as `bash ~/Downloads/stepN_files.sh`,
  followed by verification commands. Long terminal pastes proved unreliable.

## Environment
- macOS 26 (arm64), zsh; conda `(base)` active but unused by the project
- uv 0.12.19, Python 3.12.14 (uv-managed), Docker 29.6.2 / Compose v5.3.1
- Ports 5432/8000 belong to another project → RecallGraph uses **5433** (Postgres) and **8001** (API)

## Architecture (current)
Modular monolith; FastAPI app factory `recallgraph.main:create_app`.
- `core/` config (`RECALLGRAPH_*`), structlog JSON logging, `X-Request-ID` middleware,
  RFC 9457 problem details (`problems.py`)
- `db/` declarative `Base` with naming convention, async engine/session factory,
  `registry.py` (imports all models for Alembic)
- `provenance/` `Source`, `IngestionRun`, `RawRecord` models; canonical JSON SHA-256 hashing;
  repositories: `SourceRepository.upsert`, `IngestionRunRepository.start/finish`,
  `RawRecordRepository.upsert_many` (idempotent; ON CONFLICT + `xmax = 0` insert detection)
- `api/v1/` health, readiness
- Postgres 17 via `docker-compose.yml` (volume `pgdata`; `recallgraph` + `recallgraph_test` DBs)

## Endpoints
| Method | Path | Notes |
|---|---|---|
| GET | /api/v1/health | liveness |
| GET | /api/v1/ready | DB `SELECT 1` with timeout; 200 or 503 problem |

## Migrations
- `0001_baseline` — empty chain start
- `0002_provenance` — `sources`, `ingestion_runs` (status check, counts check, source/started
  index), `raw_records` (unique `(source_id, source_record_id, content_hash)`, SHA-256 length
  check, FKs to runs with RESTRICT)
- `make migrate-check` / CI run `alembic check` to prove models match migrations

## Tests
Unit: config, health, problems, request context, readiness-503, hashing.
Integration (`-m integration`, real Postgres test DB, tables truncated per test): readiness 200,
migration round trip, session factory, provenance repositories (idempotency, versioning,
in-batch dedupe, run lifecycle, DB check constraint).

## Verification results (actual output)
- Step 3 (2026-09-26): `make check` → 13 passed; live health 200, 404 problem+json.
- Step 4 (2026-09-26): CI run 36250702446 green. Commits 65445f5, 41d8351.
- Step 5 (2026-09-26): 17 passed locally; `/ready` 200 with DB up, 503 with DB stopped;
  CI run 36251076934 green (Postgres service, migrations, tests). Commit 858c552.
- Step 6 (2026-09-26): 29 passed; `alembic check` clean; CI run 36251537766 green. Commit 422eb0c.

## Key decisions
`docs/DECISIONS.md` D-001 … D-007.

## Known issues
None.

## Measured metrics
None yet. Only metrics with evidence under `evidence/` may be claimed.
