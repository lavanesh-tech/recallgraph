"""Recall search and detail queries: PostgreSQL full-text search + pg_trgm, deterministic SQL."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import (
    ColumnElement,
    Float,
    cast,
    exists,
    false,
    func,
    literal_column,
    null,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from recallgraph.normalization.text import normalize_company_name, normalize_identifier
from recallgraph.provenance.models import RawRecord, Source
from recallgraph.recalls.models import Company, Recall, RecallCompany, RecallIdentifier

_TS_CONFIG: ColumnElement[Any] = literal_column("'english'::regconfig")


@dataclass(frozen=True, slots=True)
class SearchCriteria:
    q: str | None = None
    source: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    limit: int = 20
    offset: int = 0


@dataclass(frozen=True, slots=True)
class SearchHit:
    recall: Recall
    source: str
    score: float | None
    companies: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SearchPage:
    total: int
    hits: list[SearchHit]


@dataclass(frozen=True, slots=True)
class RecallDetail:
    recall: Recall
    source: Source
    raw: RawRecord
    companies: list[tuple[str, str]]


def _tsquery(q: str) -> ColumnElement[Any]:
    return func.websearch_to_tsquery(_TS_CONFIG, q)


def _conditions(c: SearchCriteria) -> list[ColumnElement[Any]]:
    conds: list[ColumnElement[Any]] = []
    if c.source:
        conds.append(Source.code == c.source)
    if c.date_from:
        conds.append(Recall.recall_date >= c.date_from)
    if c.date_to:
        conds.append(Recall.recall_date <= c.date_to)
    if c.manufacturer:
        key = normalize_company_name(c.manufacturer)
        conds.append(
            exists().where(
                RecallCompany.recall_id == Recall.id,
                RecallCompany.company_id == Company.id,
                Company.normalized_name.contains(key, autoescape=True),
            )
            if key
            else false()
        )
    if c.model:
        key = normalize_identifier(c.model)
        conds.append(
            exists().where(
                RecallIdentifier.recall_id == Recall.id,
                RecallIdentifier.normalized_value == key,
            )
            if key
            else false()
        )
    if c.q:
        # Stemmed full-text match OR typo-tolerant trigram word similarity on the title.
        conds.append(or_(Recall.search_vector.op("@@")(_tsquery(c.q)), Recall.title.op("%>")(c.q)))
    return conds


async def _companies(
    session: AsyncSession, recall_ids: list[int]
) -> dict[int, list[tuple[str, str]]]:
    if not recall_ids:
        return {}
    rows = await session.execute(
        select(RecallCompany.recall_id, RecallCompany.role, Company.display_name)
        .join(Company, Company.id == RecallCompany.company_id)
        .where(RecallCompany.recall_id.in_(recall_ids))
        .order_by(RecallCompany.id)
    )
    by_recall: dict[int, list[tuple[str, str]]] = {}
    for recall_id, role, name in rows:
        by_recall.setdefault(recall_id, []).append((role, name))
    return by_recall


async def search_recalls(session: AsyncSession, c: SearchCriteria) -> SearchPage:
    conds = _conditions(c)
    matching = select(Recall.id).join(Source, Source.id == Recall.source_id).where(*conds)
    total: int = (
        await session.execute(select(func.count()).select_from(matching.subquery()))
    ).scalar_one()

    order: list[Any]
    score: ColumnElement[Any]
    if c.q:
        score = func.ts_rank_cd(
            Recall.search_vector, _tsquery(c.q), type_=Float
        ) + func.word_similarity(c.q, Recall.title, type_=Float)
        order = [score.desc(), Recall.recall_date.desc().nulls_last(), Recall.id.desc()]
    else:
        score = cast(null(), Float)
        order = [Recall.recall_date.desc().nulls_last(), Recall.id.desc()]

    rows = (
        await session.execute(
            select(Recall, Source.code, score.label("score"))
            .join(Source, Source.id == Recall.source_id)
            .where(*conds)
            .order_by(*order)
            .limit(c.limit)
            .offset(c.offset)
        )
    ).all()
    companies = await _companies(session, [row[0].id for row in rows])
    hits = [
        SearchHit(
            recall=recall,
            source=source_code,
            score=round(float(score_value), 4) if score_value is not None else None,
            companies=companies.get(recall.id, []),
        )
        for recall, source_code, score_value in rows
    ]
    return SearchPage(total=total, hits=hits)


async def get_recall_detail(session: AsyncSession, recall_id: int) -> RecallDetail | None:
    recall = (
        await session.execute(
            select(Recall)
            .where(Recall.id == recall_id)
            .options(
                selectinload(Recall.products),
                selectinload(Recall.hazards),
                selectinload(Recall.remedies),
                selectinload(Recall.identifiers),
            )
        )
    ).scalar_one_or_none()
    if recall is None:
        return None
    source, raw = (
        await session.execute(
            select(Source, RawRecord)
            .join(RawRecord, RawRecord.source_id == Source.id)
            .where(RawRecord.id == recall.raw_record_id)
        )
    ).one()
    companies = await _companies(session, [recall.id])
    return RecallDetail(
        recall=recall, source=source, raw=raw, companies=companies.get(recall.id, [])
    )
