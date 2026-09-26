# Architecture Decisions

Short decision records. Each entry: context, decision, consequences.

## D-001 Modular monolith first
- **Context:** Early project; no proven need for independent deployment or scaling of parts.
- **Decision:** One FastAPI service with explicit module boundaries (api, core, and later
  ingestion, normalization, search, matching). Ingestion runs as CLI jobs.
- **Consequences:** Simple to run, test and deploy. Components can be split later if a measured
  need appears.

## D-002 Official data is the only source of recall truth
- **Context:** An LLM can hallucinate recalls or miss them.
- **Decision:** Recall existence is determined only by ingested, provenance-tracked government
  records. AI may only explain retrieved evidence. "No match found" is never presented as "safe".
- **Consequences:** Matching and search must be deterministic and testable; AI features are
  additive and optional.

## D-003 uv for Python toolchain
- **Context:** Several Python installations exist on the dev machine (conda, Homebrew, python.org).
- **Decision:** uv manages Python 3.12, the virtualenv and `uv.lock`;
  `python-preference = "only-managed"`. CI installs from the lockfile (`uv sync --locked`).
- **Consequences:** Reproducible environments locally and in CI.

## D-004 RFC 9457 problem details for all errors
- **Decision:** All errors are `application/problem+json` with `type`, `title`, `status`,
  `detail`, `instance`, plus `request_id`. Generic HTTP errors use `about:blank`; validation
  errors use `urn:recallgraph:problem:validation-error` with an `errors` list (loc/msg/type
  only; rejected input is never echoed). 500s never include exception details.
- **Consequences:** Clients handle one error format; responses do not leak internals.

## D-005 Correlation IDs
- **Decision:** `X-Request-ID` is accepted only if it matches `[A-Za-z0-9._-]{1,64}`; otherwise a
  UUID4 hex is generated. It is bound to every structured log line and returned in responses.
- **Consequences:** Requests are traceable across logs; untrusted header values cannot inject
  into logs.

## D-006 Local ports 8001 (API) and 5433 (PostgreSQL)
- **Context:** Ports 8000 and 5432 are used by another local project.
- **Decision:** Use 8001 and 5433, configurable via settings/Makefile.

## D-007 Deliberately postponed technologies
Kafka, Redis, pgvector, OpenAI/LangChain, Next.js, AWS/Terraform and OpenTelemetry are
introduced only at their roadmap step and only when justified (Kafka requires a documented
justification check; pgvector must improve measured matching quality). Neo4j and Kubernetes are
not planned.

## D-008 Search on PostgreSQL (FTS + pg_trgm), no search engine
- **Context:** ~40k normalized recalls; need keyword, typo-tolerant and structured search.
- **Decision:** A generated, weighted `tsvector` (title A, description B) with a GIN index and
  `websearch_to_tsquery`, OR a pg_trgm word-similarity match on the title (GIN `gin_trgm_ops`).
  Structured filters (source, manufacturer, model identifier, date range) are SQL predicates.
  Offset pagination capped at 10,000. Every response carries a disclaimer that an empty result
  is not a safety determination.
- **Consequences:** No extra infrastructure (Elasticsearch/OpenSearch) to run. Revisit only if
  measured latency or relevance (Step 13 evaluation) shows PostgreSQL is insufficient.
