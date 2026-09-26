"""Safety history: per-company recall history and year-by-year recall timelines."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import ColumnElement, Integer, cast, distinct, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from recallgraph.normalization.text import normalize_company_name
from recallgraph.provenance.models import Source
from recallgraph.recalls.models import Company, Recall, RecallCompany
from recallgraph.search.service import SearchCriteria, SearchHit, _companies, _conditions


@dataclass(frozen=True, slots=True)
class CompanyMatch:
    id: int
    name: str
    normalized_name: str
    recall_count: int


@dataclass(frozen=True, slots=True)
class YearBucket:
    year: int | None
    source: str
    count: int


@dataclass(frozen=True, slots=True)
class CompanyHistory:
    company: Company
    total: int
    first_recall_date: date | None
    last_recall_date: date | None
    buckets: list[YearBucket]
    roles: list[tuple[str, int]]
    recent: list[SearchHit]


def _year() -> ColumnElement[Any]:
    return cast(extract("year", Recall.recall_date), Integer)


async def _year_buckets(session: AsyncSession, conds: list[ColumnElement[Any]]) -> list[YearBucket]:
    year = _year().label("year")
    count = func.count(Recall.id).label("n")
    rows = await session.execute(
        select(year, Source.code, count)
        .join(Source, Source.id == Recall.source_id)
        .where(*conds)
        .group_by(year, Source.code)
        .order_by(year.asc().nulls_last(), Source.code)
    )
    return [YearBucket(year=y, source=s, count=n) for y, s, n in rows]


async def recall_timeline(session: AsyncSession, c: SearchCriteria) -> list[YearBucket]:
    """Recall counts per year and source for the same criteria the search endpoint accepts."""
    return await _year_buckets(session, _conditions(c))


async def find_companies(session: AsyncSession, query: str, limit: int) -> list[CompanyMatch]:
    key = normalize_company_name(query)
    if not key:
        return []
    recall_count = func.count(distinct(RecallCompany.recall_id)).label("recall_count")
    rows = await session.execute(
        select(Company.id, Company.display_name, Company.normalized_name, recall_count)
        .join(RecallCompany, RecallCompany.company_id == Company.id)
        .where(Company.normalized_name.contains(key, autoescape=True))
        .group_by(Company.id)
        .order_by(recall_count.desc(), Company.display_name, Company.id)
        .limit(limit)
    )
    return [
        CompanyMatch(id=i, name=name, normalized_name=norm, recall_count=n)
        for i, name, norm, n in rows
    ]


async def company_history(
    session: AsyncSession, company_id: int, recent_limit: int = 10
) -> CompanyHistory | None:
    company = await session.get(Company, company_id)
    if company is None:
        return None
    linked = select(RecallCompany.recall_id).where(RecallCompany.company_id == company_id)
    in_company = Recall.id.in_(linked)

    total, first, last = (
        await session.execute(
            select(
                func.count(Recall.id), func.min(Recall.recall_date), func.max(Recall.recall_date)
            ).where(in_company)
        )
    ).one()
    roles = await session.execute(
        select(RecallCompany.role, func.count(distinct(RecallCompany.recall_id)))
        .where(RecallCompany.company_id == company_id)
        .group_by(RecallCompany.role)
        .order_by(RecallCompany.role)
    )
    recent_rows = (
        await session.execute(
            select(Recall, Source.code)
            .join(Source, Source.id == Recall.source_id)
            .where(in_company)
            .order_by(Recall.recall_date.desc().nulls_last(), Recall.id.desc())
            .limit(recent_limit)
        )
    ).all()
    companies = await _companies(session, [recall.id for recall, _ in recent_rows])
    return CompanyHistory(
        company=company,
        total=total,
        first_recall_date=first,
        last_recall_date=last,
        buckets=await _year_buckets(session, [in_company]),
        roles=[(role, n) for role, n in roles],
        recent=[
            SearchHit(recall=r, source=s, score=None, companies=companies.get(r.id, []))
            for r, s in recent_rows
        ],
    )
