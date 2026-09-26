# PROJECT_STATE — RecallGraph

Handoff document for continuing work in a new conversation. Keep it current after every step.

## Snapshot
- **Repo:** `~/Desktop/recallgraph` → https://github.com/lavanesh-tech/recallgraph (public)
- **Current step:** 24 of 32 — End-to-end tests and coverage (next)
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
| GET | /api/v1/recalls | FTS + pg_trgm search; filters source, manufacturer, model, date_from/to; limit<=100, offset<=10000 |
| GET | /api/v1/recalls/{id} | detail with products, hazards, remedies, identifiers, companies, provenance |
| GET | /api/v1/recalls/{id}/source-record | exact raw authoritative payload |
| GET | /api/v1/recalls/timeline | per-year, per-source recall counts for the search filters |
| GET | /api/v1/companies?q= | company search ranked by recall count |
| GET | /api/v1/companies/{id}/history | totals, first/last date, by year, by role, recent recalls |
| POST | /api/v1/match | explainable product-to-recall matching (tiers, per-signal evidence) |
| POST | /api/v1/auth/register | Argon2id user registration (201, 409, 422) |
| POST | /api/v1/auth/login | access JWT (15 min) + rotating refresh token |
| POST | /api/v1/auth/refresh | one-time refresh rotation; reuse revokes the family |
| POST | /api/v1/auth/logout | revokes the session family (204) |
| GET | /api/v1/auth/me | current user (Bearer) |
| POST/GET | /api/v1/inventory | create (limit 200/user) / list own items (Bearer) |
| GET/PATCH/DELETE | /api/v1/inventory/{id} | own items only; others are 404 |
| GET | /api/v1/inventory/{id}/matches | explainable matches for a saved item |
| GET | /api/v1/radar/alerts | own alerts (unread_only, pagination, unread count) |
| POST | /api/v1/radar/alerts/{id}/read | mark one read (others 404) |
| POST | /api/v1/radar/alerts/read-all | mark all own alerts read |
| POST | /api/v1/recalls/{id}/explanation | grounded, cited explanation (Bearer); template fallback |

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
- Step 7 (2026-09-26): 43 passed; CI run 36252101604 green; real CPSC ingestion 10,027 records in 57 year windows (55.4 s); idempotent re-run inserted 0 of 879. Evidence: evidence/ingestion/. Commits c447760, 5381a37.
- Step 8 (2026-09-26): 65 passed; CI green; 10,027 CPSC recalls normalized (0 rejected, 5.5 s); idempotent re-run 10,027 unchanged. Evidence: evidence/ingestion/cpsc-normalization.json. Commits dfa11bd, bb7a34b.
- Step 9 (2026-09-26): 75 passed; NHTSA adapter via common SourceAdapter; 30,321 NHTSA + 10,027 CPSC = 40,348 normalized recalls, 0 rejected; idempotent re-run inserted 0. Evidence: evidence/ingestion/nhtsa-idempotent-rerun-and-multisource-counts.json.

## Key decisions
`docs/DECISIONS.md` D-001 … D-007.

## Known issues
None.

## Measured metrics
- Semantic retrieval experiment (test split): F1 0.7802 -> 0.7784, recall 0.986 -> 1.0, hit@1 0.930 -> 0.937; rejected by pre-registered rule (evidence/experiments/semantic-retrieval-step19.json).
- Matching (eval-v1 held-out test split, strict): precision 0.226 -> 0.646, F1 0.368 -> 0.780, recall 0.986, hit@1 0.888 -> 0.930, negative-query FPR 0.0 (evidence/evaluation/tuning-match-1-vs-match-2.json).
- Identifier matching: precision 1.0, recall 1.0 (150 cases).
- Data: 40,348 normalized recalls from CPSC (10,027) + NHTSA (30,321).
None yet. Only metrics with evidence under `evidence/` may be claimed.
