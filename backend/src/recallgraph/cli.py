"""Command-line interface.

  recallgraph ingest cpsc --from-year 1970 [--to-year 2026]
  recallgraph ingest nhtsa [--page-size 5000] [--max-pages N]
  recallgraph normalize {cpsc,nhtsa} [--force]
  recallgraph stats

Results are printed to stdout as JSON; logs go to stderr.
"""

import argparse
import asyncio
import json
import sys
import time
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import distinct
from sqlalchemy import func as func
from sqlalchemy import select as select

from recallgraph.core.config import Settings, get_settings
from recallgraph.core.logging_config import configure_logging
from recallgraph.db.base import Base
from recallgraph.db.session import create_engine, create_session_factory
from recallgraph.evaluation.dataset import DATASET_FORMAT, build_dataset, write_dataset
from recallgraph.evaluation.runner import run_evaluation
from recallgraph.events.senders import SmtpSender
from recallgraph.events.worker import dead_letters, process_batch, queue_depth, replay_dead
from recallgraph.explain.llm import OpenAIClient
from recallgraph.explain.service import explain
from recallgraph.ingestion.runner import IngestionSummary, ingest_cpsc, run_ingestion
from recallgraph.ingestion.sources.cpsc import CpscRecallClient, year_windows
from recallgraph.ingestion.sources.nhtsa import NhtsaAdapter, NhtsaRecallClient
from recallgraph.matching.service import SemanticContext
from recallgraph.normalization.service import NORMALIZERS, normalize_source_records
from recallgraph.provenance.models import IngestionRun, RawRecord, Source
from recallgraph.radar.service import run_radar
from recallgraph.recalls.models import (
    Company,
    Recall,
    RecallCompany,
    RecallHazard,
    RecallIdentifier,
    RecallProduct,
    RecallRemedy,
)
from recallgraph.search.service import get_recall_detail
from recallgraph.semantic.embedder import FastEmbedder
from recallgraph.semantic.index import build_embeddings

# Pre-registered for the Step 19 experiment (docs/experiments/semantic-retrieval.md).
SEMANTIC_SIGNAL_WEIGHT = 0.15


async def _semantic_build(settings: Settings) -> dict[str, Any]:
    engine = create_engine(settings)
    try:
        stats = await build_embeddings(create_session_factory(engine), FastEmbedder())
    finally:
        await engine.dispose()
    return {"model": FastEmbedder.model_name, **asdict(stats)}


def _http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(60.0, connect=10.0),
        follow_redirects=True,
        headers={
            "Accept": "application/json",
            "User-Agent": (
                f"RecallGraph/{version('recallgraph')} "
                "(+https://github.com/lavanesh-tech/recallgraph)"
            ),
        },
    )


def _summary_json(summary: IngestionSummary) -> dict[str, Any]:
    seen = summary.counts.seen
    return {
        "run_id": str(summary.run_id),
        "source": summary.source,
        "status": summary.status,
        "batches": summary.windows,
        "records_seen": seen,
        "records_inserted": summary.counts.inserted,
        "records_unchanged": summary.counts.unchanged,
        "duration_s": summary.duration_s,
        "records_per_s": round(seen / summary.duration_s, 1) if summary.duration_s else None,
    }


async def _ingest(settings: Settings, args: argparse.Namespace) -> dict[str, Any]:
    engine = create_engine(settings)
    try:
        async with _http_client() as http:
            factory = create_session_factory(engine)
            if args.source == "cpsc":
                summary = await ingest_cpsc(
                    factory, CpscRecallClient(http), year_windows(args.from_year, args.to_year)
                )
            else:
                adapter = NhtsaAdapter(
                    NhtsaRecallClient(http), page_size=args.page_size, max_pages=args.max_pages
                )
                summary = await run_ingestion(factory, adapter)
    finally:
        await engine.dispose()
    return _summary_json(summary)


async def _normalize(settings: Settings, source: str, force: bool) -> dict[str, Any]:
    engine = create_engine(settings)
    started = time.perf_counter()
    try:
        counts = await normalize_source_records(create_session_factory(engine), source, force=force)
    finally:
        await engine.dispose()
    duration = round(time.perf_counter() - started, 3)
    return {
        "source": source,
        "normalizer_version": NORMALIZERS[source][1],
        "force": force,
        **asdict(counts),
        "duration_s": duration,
        "records_per_s": round(counts.seen / duration, 1) if duration else None,
    }


async def _count(session: Any, model: type[Base]) -> int:
    result = await session.execute(select(func.count()).select_from(model))
    count: int = result.scalar_one()
    return count


async def _stats(settings: Settings) -> dict[str, Any]:
    engine = create_engine(settings)
    try:
        async with create_session_factory(engine)() as session:
            per_source = (
                await session.execute(
                    select(
                        Source.code,
                        func.count(distinct(RawRecord.source_record_id)),
                        func.count(RawRecord.id),
                    )
                    .join(RawRecord, RawRecord.source_id == Source.id, isouter=True)
                    .group_by(Source.code)
                    .order_by(Source.code)
                )
            ).all()
            runs = (
                await session.execute(
                    select(IngestionRun.status, func.count()).group_by(IngestionRun.status)
                )
            ).all()
            normalized = {
                "recalls": await _count(session, Recall),
                "recall_products": await _count(session, RecallProduct),
                "recall_hazards": await _count(session, RecallHazard),
                "recall_remedies": await _count(session, RecallRemedy),
                "recall_identifiers": await _count(session, RecallIdentifier),
                "recall_company_links": await _count(session, RecallCompany),
                "companies": await _count(session, Company),
            }
    finally:
        await engine.dispose()
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "sources": {
            code: {"distinct_records": records, "stored_versions": versions}
            for code, records, versions in per_source
        },
        "ingestion_runs_by_status": {status: count for status, count in runs},
        "normalized": normalized,
    }


async def _eval_build(settings: Settings, args: argparse.Namespace) -> dict[str, Any]:
    engine = create_engine(settings)
    try:
        async with create_session_factory(engine)() as session:
            cases = await build_dataset(
                session,
                seed=args.seed,
                identifiers=args.identifiers,
                products=args.products,
                negatives=args.negatives,
            )
    finally:
        await engine.dispose()
    out = Path(args.out)
    write_dataset(out, cases)
    kinds: dict[str, int] = {}
    for case in cases:
        kinds[case.kind] = kinds.get(case.kind, 0) + 1
    return {
        "format": DATASET_FORMAT,
        "path": str(out),
        "seed": args.seed,
        "cases": len(cases),
        "by_kind": kinds,
    }


async def _eval_run(settings: Settings, args: argparse.Namespace) -> dict[str, Any]:
    engine = create_engine(settings)
    try:
        semantic = None
        if args.variant != "baseline":
            semantic = SemanticContext(
                embedder=FastEmbedder(),
                add_candidates=True,
                weight=SEMANTIC_SIGNAL_WEIGHT if args.variant == "semantic-signal" else 0.0,
            )
        report = await run_evaluation(
            create_session_factory(engine),
            Path(args.dataset),
            limit=args.limit,
            split=args.split,
            semantic=semantic,
            variant=args.variant,
        )
    finally:
        await engine.dispose()
    return report


async def _radar_run(settings: Settings) -> dict[str, Any]:
    engine = create_engine(settings)
    try:
        summary = await run_radar(create_session_factory(engine))
    finally:
        await engine.dispose()
    return {
        "run_id": str(summary.run_id) if summary.run_id else None,
        "status": summary.status,
        "recalls_scanned": summary.recalls_scanned,
        "items_scanned": summary.items_scanned,
        "alerts_created": summary.alerts_created,
        "duration_s": summary.duration_s,
    }


async def _radar_cycle(settings: Settings, cpsc_from_year: int) -> dict[str, Any]:
    """Scheduled job: incremental ingestion of both sources, normalization, radar run."""
    this_year = datetime.now(UTC).year
    cpsc = argparse.Namespace(source="cpsc", from_year=cpsc_from_year, to_year=this_year)
    nhtsa = argparse.Namespace(source="nhtsa", page_size=5000, max_pages=None)
    return {
        "ingest": [await _ingest(settings, cpsc), await _ingest(settings, nhtsa)],
        "normalize": [
            await _normalize(settings, "cpsc", False),
            await _normalize(settings, "nhtsa", False),
        ],
        "radar": await _radar_run(settings),
    }


async def _worker(settings: Settings, args: argparse.Namespace) -> dict[str, Any]:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    sender = SmtpSender(settings.smtp_host, settings.smtp_port, settings.mail_from)
    totals: dict[str, Any] = {
        "batches": 0,
        "claimed": 0,
        "sent": 0,
        "duplicates": 0,
        "skipped": 0,
        "retried": 0,
        "dead": 0,
    }
    try:
        if args.worker_command == "dead-letters":
            async with factory() as session:
                return {"dead_letters": await dead_letters(session)}
        if args.worker_command == "replay":
            async with factory() as session:
                event_id = uuid.UUID(args.event_id) if args.event_id else None
                return {"replayed": await replay_dead(session, event_id)}
        if args.worker_command == "status":
            async with factory() as session:
                return {"queue": await queue_depth(session)}
        while True:
            stats = await process_batch(factory, sender, batch_size=args.batch_size)
            totals["batches"] += 1
            for key, value in asdict(stats).items():
                if key in totals:
                    totals[key] += value
            if args.once or (args.drain and stats.claimed == 0):
                return totals
            if stats.claimed == 0:
                await asyncio.sleep(args.interval)
    finally:
        await engine.dispose()


async def _explain_eval(settings: Settings, sample: int, seed: int) -> dict[str, Any]:
    """Opt-in: calls the real OpenAI API for `sample` recalls (costs money)."""
    if settings.openai_api_key is None:
        raise SystemExit("RECALLGRAPH_OPENAI_API_KEY is not set; nothing was called.")
    llm = OpenAIClient(
        settings.openai_api_key.get_secret_value(), settings.openai_model, settings.openai_timeout_s
    )
    engine = create_engine(settings)
    counts = {"llm": 0, "template_fallback": 0, "insufficient_on_offtopic": 0, "points": 0}
    reasons: dict[str, int] = {}
    started = time.perf_counter()
    try:
        async with create_session_factory(engine)() as session:
            ids = (
                (
                    await session.execute(
                        select(Recall.id)
                        .order_by(func.md5(func.concat(Recall.id, f":{seed}")))
                        .limit(sample)
                    )
                )
                .scalars()
                .all()
            )
            for recall_id in ids:
                detail = await get_recall_detail(session, recall_id)
                if detail is None:
                    continue
                grounded = await explain(detail, llm)
                counts["llm" if grounded.mode == "llm" else "template_fallback"] += 1
                counts["points"] += len(grounded.points)
                if grounded.fallback_reason:
                    key = grounded.fallback_reason.split(":")[-1].strip()
                    reasons[key] = reasons.get(key, 0) + 1
                offtopic = await explain(detail, llm, "What will this product cost in 2035?")
                counts["insufficient_on_offtopic"] += int(
                    offtopic.mode == "llm" and offtopic.insufficient_evidence
                )
    finally:
        await engine.dispose()
    n = len(ids)
    return {
        "model": settings.openai_model,
        "sample": n,
        "seed": seed,
        "grounded_pass_rate": round(counts["llm"] / n, 4) if n else None,
        "fallback_reasons": reasons,
        "offtopic_refusal_rate": round(counts["insufficient_on_offtopic"] / n, 4) if n else None,
        "mean_points": round(counts["points"] / n, 2) if n else None,
        "duration_s": round(time.perf_counter() - started, 2),
        "note": "grounded = every point cites valid evidence ids and no safety claims (guard)",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="recallgraph")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="ingest an authoritative source")
    ingest_sources = ingest.add_subparsers(dest="source", required=True)
    cpsc = ingest_sources.add_parser("cpsc", help="CPSC recalls (SaferProducts.gov)")
    cpsc.add_argument("--from-year", type=int, required=True)
    cpsc.add_argument("--to-year", type=int, default=datetime.now(UTC).year)
    nhtsa = ingest_sources.add_parser("nhtsa", help="NHTSA recalls (data.transportation.gov)")
    nhtsa.add_argument("--page-size", type=int, default=5000)
    nhtsa.add_argument("--max-pages", type=int, default=None)

    normalize = commands.add_parser("normalize", help="normalize ingested raw records")
    normalize.add_argument("source", choices=sorted(NORMALIZERS))
    normalize.add_argument("--force", action="store_true", help="re-normalize everything")

    commands.add_parser("stats", help="print dataset and ingestion-run counts")

    evaluation = commands.add_parser("eval", help="matching evaluation")
    eval_commands = evaluation.add_subparsers(dest="eval_command", required=True)
    build = eval_commands.add_parser("build", help="build a labeled evaluation set")
    build.add_argument("--out", required=True)
    build.add_argument("--seed", type=int, default=13)
    build.add_argument("--identifiers", type=int, default=150)
    build.add_argument("--products", type=int, default=150)
    build.add_argument("--negatives", type=int, default=100)
    run = eval_commands.add_parser("run", help="evaluate the matching engine")
    run.add_argument("--dataset", required=True)
    run.add_argument("--limit", type=int, default=20)
    run.add_argument("--split", choices=["dev", "test"], default=None)
    run.add_argument(
        "--variant",
        choices=["baseline", "semantic-candidates", "semantic-signal"],
        default="baseline",
    )

    semantic_cmd = commands.add_parser("semantic", help="embedding index (experiment)")
    semantic_commands = semantic_cmd.add_subparsers(dest="semantic_command", required=True)
    semantic_commands.add_parser("build", help="embed recall product text into pgvector")
    explain_cmd = commands.add_parser("explain", help="grounded explanation evaluation")
    explain_commands = explain_cmd.add_subparsers(dest="explain_command", required=True)
    explain_eval = explain_commands.add_parser("eval", help="OPT-IN: calls OpenAI")
    explain_eval.add_argument("--sample", type=int, default=20)
    explain_eval.add_argument("--seed", type=int, default=20)

    radar = commands.add_parser("radar", help="Recall Radar")
    radar_commands = radar.add_subparsers(dest="radar_command", required=True)
    radar_commands.add_parser("run", help="match new recalls and changed items")
    cycle = radar_commands.add_parser("cycle", help="ingest + normalize + radar run")
    cycle.add_argument("--cpsc-from-year", type=int, default=datetime.now(UTC).year - 1)

    worker = commands.add_parser("worker", help="outbox notification worker")
    worker_commands = worker.add_subparsers(dest="worker_command", required=True)
    work = worker_commands.add_parser("run", help="deliver pending outbox events")
    work.add_argument("--once", action="store_true", help="process one batch")
    work.add_argument("--drain", action="store_true", help="stop when the queue is empty")
    work.add_argument("--batch-size", type=int, default=50)
    work.add_argument("--interval", type=float, default=5.0)
    worker_commands.add_parser("status", help="outbox queue depth by status")
    worker_commands.add_parser("dead-letters", help="list dead-lettered events")
    replay = worker_commands.add_parser("replay", help="requeue dead-lettered events")
    replay.add_argument("--event-id", default=None)
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json, stream=sys.stderr)
    if args.command == "ingest":
        result = asyncio.run(_ingest(settings, args))
    elif args.command == "normalize":
        result = asyncio.run(_normalize(settings, args.source, args.force))
    elif args.command == "eval" and args.eval_command == "build":
        result = asyncio.run(_eval_build(settings, args))
    elif args.command == "eval":
        result = asyncio.run(_eval_run(settings, args))
    elif args.command == "radar" and args.radar_command == "run":
        result = asyncio.run(_radar_run(settings))
    elif args.command == "radar":
        result = asyncio.run(_radar_cycle(settings, args.cpsc_from_year))
    elif args.command == "worker":
        result = asyncio.run(_worker(settings, args))
    elif args.command == "semantic":
        result = asyncio.run(_semantic_build(settings))
    elif args.command == "explain":
        result = asyncio.run(_explain_eval(settings, args.sample, args.seed))
    else:
        result = asyncio.run(_stats(settings))
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0
