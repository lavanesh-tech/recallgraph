# Benchmarks

Reproduce (real CPSC + NHTSA data loaded, API on 127.0.0.1:8001 as a single uvicorn process):

    make db-up && (cd backend && uv run uvicorn recallgraph.main:create_app --factory --port 8001) &
    make bench

Workload: fixed request lists cycled for keyword search, filtered search, description matching
and recall detail; 400 measured requests per scenario at concurrency 1, 8 and 32 after a
discarded warm-up. Results, machine and commit: `evidence/benchmarks/api-latency.json`.

Caveats: load generator and server share one laptop, so these are relative numbers for
regression tracking, not production capacity.

## Findings (see evidence file for full numbers)
- Search and recall detail stay under ~200 ms p99 at concurrency 32 on one process.
- Description matching saturates at ~50 req/s (p95 ~1 s at concurrency 32): candidate scoring
  is CPU-bound Python in a single process. Levers, in order: more API processes/tasks, smaller
  candidate sets, caching per query. Not optimised yet; recorded as the known bottleneck.
