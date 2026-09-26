"""Runs the matching engine over an evaluation set and reports metrics."""

import hashlib
import time
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from recallgraph.evaluation.dataset import EvalCase, read_dataset, split_of
from recallgraph.evaluation.metrics import CaseOutcome, evaluate
from recallgraph.matching.engine import (
    ENGINE_VERSION,
    IDENTITY_MIN,
    LIKELY_THRESHOLD,
    POSSIBLE_THRESHOLD,
    PRODUCT_EVIDENCE_MIN,
    WEIGHTS,
    MatchQuery,
)
from recallgraph.matching.service import match_product


async def run_cases(
    session_factory: async_sessionmaker[AsyncSession], cases: list[EvalCase], limit: int
) -> list[CaseOutcome]:
    outcomes: list[CaseOutcome] = []
    async with session_factory() as session:
        for case in cases:
            outcome = await match_product(session, MatchQuery(**case.query), limit)
            outcomes.append(
                CaseOutcome(
                    case_id=case.case_id,
                    kind=case.kind,
                    expected=frozenset((code, sid) for code, sid in case.expected),
                    ranked=tuple(
                        ((r.profile.source, r.profile.source_record_id), r.tier)
                        for r in outcome.results
                    ),
                )
            )
    return outcomes


async def run_evaluation(
    session_factory: async_sessionmaker[AsyncSession],
    dataset: Path,
    limit: int = 20,
    split: str | None = None,
) -> dict[str, Any]:
    cases = [c for c in read_dataset(dataset) if split is None or split_of(c.case_id) == split]
    started = time.perf_counter()
    outcomes = await run_cases(session_factory, cases, limit)
    duration = time.perf_counter() - started
    return {
        "engine_version": ENGINE_VERSION,
        "engine_config": {
            "weights": WEIGHTS,
            "likely_threshold": LIKELY_THRESHOLD,
            "possible_threshold": POSSIBLE_THRESHOLD,
            "identity_min": IDENTITY_MIN,
            "product_evidence_min": PRODUCT_EVIDENCE_MIN,
        },
        "dataset": {
            "path": str(dataset),
            "sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
            "split": split or "all",
            "cases": len(cases),
            "by_kind": dict(sorted(Counter(c.kind for c in cases).items())),
        },
        "result_limit": limit,
        "duration_s": round(duration, 3),
        "mean_latency_ms": round(duration * 1000 / len(cases), 2) if cases else None,
        "metrics": evaluate(outcomes),
        "errors": [
            {
                "case_id": o.case_id,
                "kind": o.kind,
                "expected": sorted(o.expected),
                "top": o.ranked[:3],
            }
            for o in outcomes
            if (o.expected and not any(k in o.expected for k, t in o.ranked if t != "possible"))
            or (not o.expected and any(t != "possible" for _, t in o.ranked))
        ][:50],
    }
