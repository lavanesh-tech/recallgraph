"""Normalizes the latest raw version of every source record into the recall domain tables."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from recallgraph.normalization.cpsc import NORMALIZER_VERSION, normalize_cpsc
from recallgraph.normalization.types import NormalizedCompany, NormalizedRecall
from recallgraph.provenance.models import RawRecord, Source
from recallgraph.recalls.models import (
    Company,
    Recall,
    RecallCompany,
    RecallHazard,
    RecallIdentifier,
    RecallProduct,
    RecallRemedy,
)

logger = structlog.get_logger(__name__)

_WITH_CHILDREN = (
    selectinload(Recall.products),
    selectinload(Recall.hazards),
    selectinload(Recall.remedies),
    selectinload(Recall.identifiers),
    selectinload(Recall.companies),
)


@dataclass(slots=True)
class NormalizationCounts:
    seen: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    rejected: int = 0


async def _ensure_companies(
    session: AsyncSession, companies: Sequence[NormalizedCompany]
) -> dict[str, int]:
    unique = {c.normalized_name: c.display_name for c in companies}
    if not unique:
        return {}
    await session.execute(
        pg_insert(Company)
        .values([{"normalized_name": k, "display_name": v} for k, v in unique.items()])
        .on_conflict_do_nothing(index_elements=[Company.normalized_name])
    )
    rows = await session.execute(
        select(Company.normalized_name, Company.id).where(Company.normalized_name.in_(unique))
    )
    return {name: company_id for name, company_id in rows}


def _apply(
    recall: Recall, raw: RawRecord, n: NormalizedRecall, company_ids: dict[str, int]
) -> None:
    recall.raw_record_id = raw.id
    recall.normalizer_version = NORMALIZER_VERSION
    recall.recall_number = n.recall_number
    recall.title = n.title
    recall.description = n.description
    recall.recall_date = n.recall_date
    recall.published_date = n.published_date
    recall.url = n.url
    recall.consumer_contact = n.consumer_contact
    recall.injuries_summary = n.injuries_summary
    recall.sold_at = n.sold_at
    recall.remedy_options = list(n.remedy_options)
    recall.manufacturer_countries = list(n.manufacturer_countries)
    recall.normalized_at = datetime.now(UTC)
    recall.products = [
        RecallProduct(
            name=p.name,
            description=p.description,
            model=p.model,
            product_type=p.product_type,
            category_code=p.category_code,
            units_text=p.units_text,
        )
        for p in n.products
    ]
    recall.hazards = [
        RecallHazard(description=h.description, hazard_type=h.hazard_type) for h in n.hazards
    ]
    recall.remedies = [RecallRemedy(description=r) for r in n.remedies]
    recall.identifiers = [
        RecallIdentifier(kind=i.kind, value=i.value, normalized_value=i.normalized_value)
        for i in n.identifiers
    ]
    recall.companies = [
        RecallCompany(company_id=company_ids[c.normalized_name], role=c.role, raw_name=c.raw_name)
        for c in n.companies
    ]


async def normalize_cpsc_records(
    session_factory: async_sessionmaker[AsyncSession], *, force: bool = False, batch_size: int = 500
) -> NormalizationCounts:
    """Idempotent: a recall already built from the same raw version by the same normalizer
    version is left untouched unless force=True."""
    counts = NormalizationCounts()
    async with session_factory() as session:
        source = (
            await session.execute(select(Source).where(Source.code == "cpsc"))
        ).scalar_one_or_none()
        if source is None:
            raise LookupError("no 'cpsc' source found; run `recallgraph ingest cpsc` first")
        source_id = source.id
        latest_ids = (
            (
                await session.execute(
                    select(RawRecord.id)
                    .where(RawRecord.source_id == source_id)
                    .distinct(RawRecord.source_record_id)
                    .order_by(
                        RawRecord.source_record_id,
                        RawRecord.last_seen_at.desc(),
                        RawRecord.id.desc(),
                    )
                )
            )
            .scalars()
            .all()
        )

        for start in range(0, len(latest_ids), batch_size):
            raws = (
                (
                    await session.execute(
                        select(RawRecord).where(
                            RawRecord.id.in_(latest_ids[start : start + batch_size])
                        )
                    )
                )
                .scalars()
                .all()
            )
            existing = {
                r.source_record_id: r
                for r in (
                    await session.execute(
                        select(Recall)
                        .where(
                            Recall.source_id == source_id,
                            Recall.source_record_id.in_([r.source_record_id for r in raws]),
                        )
                        .options(*_WITH_CHILDREN)
                    )
                ).scalars()
            }

            pending: list[tuple[RawRecord, NormalizedRecall]] = []
            for raw in raws:
                counts.seen += 1
                current = existing.get(raw.source_record_id)
                if (
                    current is not None
                    and not force
                    and current.raw_record_id == raw.id
                    and current.normalizer_version == NORMALIZER_VERSION
                ):
                    counts.unchanged += 1
                    continue
                try:
                    pending.append((raw, normalize_cpsc(raw.payload)))
                except ValueError as exc:
                    counts.rejected += 1
                    logger.warning(
                        "normalization_rejected",
                        source_record_id=raw.source_record_id,
                        error=str(exc),
                    )

            company_ids = await _ensure_companies(
                session, [c for _, n in pending for c in n.companies]
            )
            for raw, normalized in pending:
                recall = existing.get(raw.source_record_id)
                if recall is None:
                    recall = Recall(source_id=source_id, source_record_id=raw.source_record_id)
                    session.add(recall)
                    counts.created += 1
                else:
                    counts.updated += 1
                _apply(recall, raw, normalized, company_ids)
            await session.commit()
            session.expunge_all()
            logger.info("normalization_batch_done", processed=counts.seen)
    return counts
