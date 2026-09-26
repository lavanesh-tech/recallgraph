"""Safety-history endpoints: company search, company history, recall timeline."""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from recallgraph.db.session import get_session
from recallgraph.history.schemas import (
    CompanyHistoryResponse,
    CompanySearchResponse,
    CompanySummary,
    RoleCount,
    TimelineResponse,
    YearBucketOut,
)
from recallgraph.history.service import (
    YearBucket,
    company_history,
    find_companies,
    recall_timeline,
)
from recallgraph.search.schemas import CompanyRef, RecallSummary
from recallgraph.search.service import SearchCriteria

companies_router = APIRouter(prefix="/companies", tags=["safety history"])
# Registered before the recalls router so "/recalls/timeline" is not parsed as a recall id.
timeline_router = APIRouter(prefix="/recalls", tags=["safety history"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _buckets(buckets: list[YearBucket]) -> list[YearBucketOut]:
    return [YearBucketOut(year=b.year, source=b.source, count=b.count) for b in buckets]


@timeline_router.get("/timeline", response_model=TimelineResponse)
async def timeline(
    session: SessionDep,
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    source: Annotated[Literal["cpsc", "nhtsa"] | None, Query()] = None,
    manufacturer: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    model: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> TimelineResponse:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to.")
    buckets = await recall_timeline(
        session,
        SearchCriteria(
            q=(q.strip() or None) if q else None,
            source=source,
            manufacturer=manufacturer,
            model=model,
            date_from=date_from,
            date_to=date_to,
        ),
    )
    return TimelineResponse(total=sum(b.count for b in buckets), buckets=_buckets(buckets))


@companies_router.get("", response_model=CompanySearchResponse)
async def search_companies(
    session: SessionDep,
    q: Annotated[str, Query(min_length=2, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> CompanySearchResponse:
    matches = await find_companies(session, q, limit)
    return CompanySearchResponse(
        items=[
            CompanySummary(
                id=m.id, name=m.name, normalized_name=m.normalized_name, recall_count=m.recall_count
            )
            for m in matches
        ]
    )


@companies_router.get("/{company_id}/history", response_model=CompanyHistoryResponse)
async def get_company_history(
    session: SessionDep, company_id: Annotated[int, Path(ge=1, le=2**31 - 1)]
) -> CompanyHistoryResponse:
    history = await company_history(session, company_id)
    if history is None:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found.")
    return CompanyHistoryResponse(
        id=history.company.id,
        name=history.company.display_name,
        normalized_name=history.company.normalized_name,
        total_recalls=history.total,
        first_recall_date=history.first_recall_date,
        last_recall_date=history.last_recall_date,
        by_year=_buckets(history.buckets),
        by_role=[RoleCount(role=role, count=n) for role, n in history.roles],
        recent_recalls=[
            RecallSummary(
                id=hit.recall.id,
                source=hit.source,
                source_record_id=hit.recall.source_record_id,
                recall_number=hit.recall.recall_number,
                title=hit.recall.title,
                recall_date=hit.recall.recall_date,
                url=hit.recall.url,
                companies=[CompanyRef(role=r, name=n) for r, n in hit.companies],
                score=None,
            )
            for hit in history.recent
        ],
    )
