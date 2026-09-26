"""Command-line interface.

  recallgraph ingest cpsc --from-year 1970 [--to-year 2026]
  recallgraph stats

Results are printed to stdout as JSON; logs go to stderr.
"""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from importlib.metadata import version
from typing import Any

import httpx
from sqlalchemy import distinct, func, select

from recallgraph.core.config import Settings, get_settings
from recallgraph.core.logging_config import configure_logging
from recallgraph.db.session import create_engine, create_session_factory
from recallgraph.ingestion.runner import ingest_cpsc
from recallgraph.ingestion.sources.cpsc import CpscRecallClient, year_windows
from recallgraph.provenance.models import IngestionRun, RawRecord, Source


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


async def _ingest_cpsc(settings: Settings, from_year: int, to_year: int) -> dict[str, Any]:
    engine = create_engine(settings)
    try:
        async with _http_client() as http:
            summary = await ingest_cpsc(
                create_session_factory(engine),
                CpscRecallClient(http),
                year_windows(from_year, to_year),
            )
    finally:
        await engine.dispose()
    seen = summary.counts.seen
    return {
        "run_id": str(summary.run_id),
        "source": summary.source,
        "status": summary.status,
        "year_windows": summary.windows,
        "records_seen": seen,
        "records_inserted": summary.counts.inserted,
        "records_unchanged": summary.counts.unchanged,
        "duration_s": summary.duration_s,
        "records_per_s": round(seen / summary.duration_s, 1) if summary.duration_s else None,
    }


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
    finally:
        await engine.dispose()
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "sources": {
            code: {"distinct_records": records, "stored_versions": versions}
            for code, records, versions in per_source
        },
        "ingestion_runs_by_status": {status: count for status, count in runs},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="recallgraph")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest", help="ingest an authoritative source")
    sources = ingest.add_subparsers(dest="source", required=True)
    cpsc = sources.add_parser("cpsc", help="CPSC recalls (SaferProducts.gov)")
    cpsc.add_argument("--from-year", type=int, required=True)
    cpsc.add_argument("--to-year", type=int, default=datetime.now(UTC).year)
    commands.add_parser("stats", help="print dataset and ingestion-run counts")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json, stream=sys.stderr)
    if args.command == "ingest":
        result = asyncio.run(_ingest_cpsc(settings, args.from_year, args.to_year))
    else:
        result = asyncio.run(_stats(settings))
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0
