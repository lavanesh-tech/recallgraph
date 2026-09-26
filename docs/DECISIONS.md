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

## D-009 Explainable, deterministic matching (engine match-1)
- **Candidates:** union of identifier (exact + model-family prefix), whole-token manufacturer,
  and OR-full-text retrieval; at most 200 per channel.
- **Signals (weight):** identifier 0.40, manufacturer 0.25, category 0.10, lexical 0.20,
  date compatibility 0.05. Score = weighted mean over *applicable* signals only; contributions
  sum to the score and every signal carries human-readable evidence.
- **Tiers:** `identifier_match` (exact model/UPC); `likely` (score >= 0.60 AND identity >= 0.6
  AND product evidence >= 0.5); `possible` (score >= 0.35); otherwise not returned.
- **Why:** no fabricated "AI confidence"; every number is reproducible and testable. Weights and
  thresholds are initial values, to change only with evidence from the labeled evaluation set.

## D-010 Matching tuning match-1 -> match-2 (evidence-driven, held-out split)
- **Method:** eval-v1 split 50/50 by SHA-256 of case id. Error analysis only on `dev`
  (`evaluation/analyze_errors.py`); `test` evaluated once before and once after.
- **Finding:** all true "likely" matches had full product-term coverage; most false positives
  came from partial coverage via generic words in long NHTSA/CPSC defect text.
- **Change:** lexical evidence uses title + product names only; `likely` needs full coverage;
  title similarity breaks score ties. Results: `evidence/evaluation/tuning-match-1-vs-match-2.json`.
- **Caveat:** product labels are incomplete (near-duplicate recalls of the same product count
  as FP), so product precision remains a lower bound.

## D-011 Authentication and authorization
- **Passwords:** Argon2id (argon2-cffi defaults), 12-128 chars; unknown-email logins verify a
  dummy hash so both failure paths cost the same; one generic 401 message.
- **Access tokens:** JWT HS256, 15 min, `iss`/`aud`/`exp`/`iat`/`jti`/`typ` required; the
  accepted algorithm is pinned server-side (no `alg: none`, no algorithm confusion).
- **Refresh tokens:** opaque random 256-bit values, stored only as SHA-256, 14 days, rotated on
  every use. Reusing a spent token revokes the whole token family (theft signal) and is audited.
  Row lock (`SELECT ... FOR UPDATE`) prevents double rotation.
- **Secrets:** the dev JWT secret is refused in staging/production (settings validation).
- **Audit log:** register, login success/failure, refresh, reuse detection, logout with request
  id and client IP; never passwords, tokens or submitted emails.
- **Known trade-off:** registration reports "email already registered" (409), which allows
  account enumeration; login is rate-limited in Step 23.

## D-012 Inventory isolation
Every inventory query filters by the authenticated user's id in SQL (never by client input).
Another user's item returns 404, not 403, so item ids cannot be probed. Request models use
`extra="forbid"` to block mass assignment (e.g. `user_id`). 200 items per user (soft limit).

## D-013 Recall Radar core (synchronous, in-database)
- A run = reverse scan (recalls normalized since the recall watermark x all items, pure
  in-memory scoring) + forward scan (items changed since the item watermark x catalog).
- Alerts only for strict tiers; `UNIQUE (inventory_item_id, recall_id)` + `ON CONFLICT DO
  NOTHING` makes runs idempotent; watermarks overlap 5 minutes to tolerate late commits.
- One transaction with `pg_try_advisory_xact_lock` prevents concurrent runs.
- Whether this needs an event-driven pipeline is evaluated in Step 18.

## D-014 Event-driven Radar: transactional outbox on PostgreSQL, not Kafka
- **Justification check (measured, `evidence/architecture/event-driven-justification.json`):**
  a few new official recalls per day across both agencies; one full scheduled cycle ~19 s;
  a single consumer (notification delivery).
- **Kafka would be justified by:** several independent consumer services, sustained throughput
  beyond what a polled PostgreSQL queue handles, or long-term event replay/stream processing.
  None applies, so Kafka would add a broker, schema/ops burden and failure modes with no
  measured benefit.
- **What IS needed:** delivery must not block or fail the radar transaction; retries; no lost
  or duplicated notifications. Implemented with a transactional outbox (alert + event in one
  transaction), a worker using `FOR UPDATE SKIP LOCKED`, exponential backoff, dead-lettering
  after 5 attempts with replay, an idempotency table (one notification per alert/channel) and
  deterministic email Message-IDs. Tested: duplicates, concurrency, crash mid-batch, DLQ.
- **Revisit** if a second consumer (e.g. push notifications, analytics) or measured load
  appears; the outbox then becomes the source for a relay into a broker.

## D-015 Semantic retrieval (pgvector) not adopted
Pre-registered experiment (`docs/experiments/semantic-retrieval.md`), eval-v1 test split:
strict F1 0.7802 (match-2) vs 0.7784 (both semantic variants): -0.0018, below the +0.02 bar.
Semantic candidates raised recall 0.986 -> 1.0 and hit@1 0.930 -> 0.937 at ~+2-7% latency,
but lowered precision. Decision: keep match-2; the embedding index and variants remain only
as a reproducible experiment (`recallgraph eval run --variant ...`), not in the API.
Evidence: `evidence/experiments/semantic-retrieval-step19.json`.

## D-016 Frontend: React + JavaScript (Vite), no Next.js
A single-page React app (JavaScript, HTML, CSS) built with Vite, talking to the existing
FastAPI REST API. No Next.js: server-side rendering and its server runtime are not needed
for a handful of authenticated pages over an existing API.

## D-017 Grounded AI explanations
- Recall truth is retrieved deterministically; the LLM only rewords a numbered evidence pack
  (title, dates, products, hazards, remedies, identifiers, contact, source) delimited as data.
- Strict JSON schema output; a guard requires >= 1 valid evidence citation per point and rejects
  safety claims ("is safe", "no recalls", "not recalled", "guarantee").
- Any LLM failure or guard rejection returns a deterministic template from the same evidence,
  with `mode` and `fallback_reason` in the response. Tests use fakes only (no network/cost);
  real calls happen only via the opt-in `recallgraph explain eval`.
- Plain OpenAI SDK, no LangChain: one structured call needs no orchestration framework.

## D-018 Security hardening scope
Pure ASGI middleware for security headers, a 64 KiB body limit and an in-process auth rate
limiter; CORS closed by default; docs disabled outside local/test. CI adds gitleaks, pip-audit
and npm audit. No external WAF/Redis yet: single instance; limitation recorded in docs/SECURITY.md.

## D-019 Containers
Multi-stage images: API/worker/migrations share one Python image (uv-locked, no dev deps,
non-root uid 10001, read-only root filesystem, all capabilities dropped); the web image is
the Vite build on unprivileged nginx, proxying `/api` so the browser stays same-origin.
Migrations run as a one-shot container before the API starts. CI builds both images and fails
on fixable CRITICAL vulnerabilities (Trivy).

## D-020 Observability
Prometheus metrics (route-template labels, outbox sampled at scrape), alert rules and a
provisioned Grafana dashboard; JSON logs with request ids. `/metrics` lives outside `/api` so the
public proxy never serves it. No OpenTelemetry tracing: a single API service plus one worker do not
need it yet (logs already correlate by request id).

Grounding evaluation (real OpenAI, opt-in, gpt-4o-mini, 20 recalls): grounded pass rate 1.0,
off-topic refusal rate 1.0, no fallbacks (evidence/explanations/grounding-eval.json).
