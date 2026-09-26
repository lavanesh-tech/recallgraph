"""Closed-loop HTTP load benchmark (stdlib + httpx). Reports only what it measured.

Usage:
  uv run python benchmarks/load.py --base-url http://127.0.0.1:8001 \
      --requests 400 --concurrency 1 8 32 --out ../evidence/benchmarks/api-latency.json
"""

import argparse
import asyncio
import json
import os
import platform
import statistics
import subprocess
import time
from datetime import UTC, datetime
from typing import Any

import httpx

# Fixed, deterministic workload. Queries are generic product terms, not tuned to the index.
SCENARIOS: dict[str, list[dict[str, Any]]] = {
    "search_keywords": [
        {"method": "GET", "url": "/api/v1/recalls", "params": {"q": q, "limit": 20}}
        for q in [
            "air fryer",
            "space heater",
            "airbag inflator",
            "baby crib",
            "lithium battery",
            "brake hose",
            "hair dryer",
            "stroller",
            "e-bike",
            "pressure cooker",
        ]
    ],
    "search_filtered": [
        {
            "method": "GET",
            "url": "/api/v1/recalls",
            "params": {"q": q, "source": src, "date_from": "2020-01-01", "limit": 20},
        }
        for q, src in [
            ("fire hazard", "cpsc"),
            ("fuel leak", "nhtsa"),
            ("choking", "cpsc"),
            ("steering", "nhtsa"),
            ("electrocution", "cpsc"),
        ]
    ],
    "match_description": [
        {"method": "POST", "url": "/api/v1/match", "json": {"description": d, "limit": 10}}
        for d in [
            "stainless steel air fryer 5 quart",
            "portable electric space heater",
            "infant sleeper inclined",
            "cordless hair dryer brush",
            "youth ATV",
        ]
    ],
    "recall_detail": [],  # filled from live search results (real ids)
}


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct / 100
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


async def _run(
    client: httpx.AsyncClient, requests: list[dict[str, Any]], total: int, concurrency: int
) -> dict[str, Any]:
    latencies: list[float] = []
    errors = 0
    counter = 0
    lock = asyncio.Lock()

    async def worker() -> None:
        nonlocal counter, errors
        while True:
            async with lock:
                if counter >= total:
                    return
                spec = requests[counter % len(requests)]
                counter += 1
            started = time.perf_counter()
            try:
                response = await client.request(**spec)
                ok = response.status_code < 400
            except httpx.HTTPError:
                ok = False
            latencies.append((time.perf_counter() - started) * 1000)
            if not ok:
                errors += 1

    started = time.perf_counter()
    await asyncio.gather(*(worker() for _ in range(concurrency)))
    elapsed = time.perf_counter() - started
    return {
        "concurrency": concurrency,
        "requests": len(latencies),
        "errors": errors,
        "throughput_rps": round(len(latencies) / elapsed, 1),
        "latency_ms": {
            "p50": round(_percentile(latencies, 50), 2),
            "p95": round(_percentile(latencies, 95), 2),
            "p99": round(_percentile(latencies, 99), 2),
            "mean": round(statistics.fmean(latencies), 2),
            "max": round(max(latencies), 2),
        },
    }


def _git_sha() -> str:
    return subprocess.run(  # noqa: S603
        ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,  # noqa: S607
    ).stdout.strip()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--requests", type=int, default=400)
    parser.add_argument("--warmup", type=int, default=30)
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 8, 32])
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    limits = httpx.Limits(max_connections=max(args.concurrency) + 4)
    async with httpx.AsyncClient(base_url=args.base_url, timeout=30, limits=limits) as client:
        found = await client.get("/api/v1/recalls", params={"q": "recall", "limit": 50})
        found.raise_for_status()
        ids = [item["id"] for item in found.json()["items"]]
        SCENARIOS["recall_detail"] = [{"method": "GET", "url": f"/api/v1/recalls/{i}"} for i in ids]
        stats = (await client.get("/api/v1/recalls", params={"limit": 1})).json()["total"]

        results: dict[str, list[dict[str, Any]]] = {}
        for name, specs in SCENARIOS.items():
            await _run(client, specs, args.warmup, 4)  # warm caches / connections, discarded
            results[name] = [await _run(client, specs, args.requests, c) for c in args.concurrency]
            best = results[name][-1]
            print(
                f"{name}: c={best['concurrency']} p95={best['latency_ms']['p95']}ms "
                f"rps={best['throughput_rps']} errors={best['errors']}"
            )

    report = {
        "recorded_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_commit": _git_sha(),
        "command": "uv run python benchmarks/load.py "
        + " ".join(
            f"--{k.replace('_', '-')} {' '.join(map(str, v)) if isinstance(v, list) else v}"
            for k, v in vars(args).items()
        ),
        "environment": {
            "machine": f"{platform.system()} {platform.machine()}",
            "cpu_count": os.cpu_count(),
            "python": platform.python_version(),
            "server": "1 uvicorn process, Postgres 17 (Docker), load generator on the same host",
            "dataset_recalls": stats,
        },
        "method": "closed-loop; fixed request list cycled; warmup discarded; errors = HTTP >= 400",
        "results": results,
        "caveat": (
            "Single-host numbers: client and server share CPUs. Not a production capacity claim."
        ),
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")


if __name__ == "__main__":
    asyncio.run(main())
