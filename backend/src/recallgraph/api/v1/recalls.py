"""Recall search, detail and source-record endpoints."""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from recallgraph.db.session import get_session
from recallgraph.search.schemas import (
    CompanyRef,
    HazardOut,
    IdentifierOut,
    ProductOut,
    ProvenanceOut,
    RecallDetailOut,
    RecallSummary,
    SearchResponse,
    SourceRecordOut,
)
from recallgraph.search.service import (
    RecallDetail,
    SearchCriteria,
    get_recall_detail,
    search_recalls,
)

router = APIRouter(prefix="/recalls", tags=["recalls"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
RecallIdPath = Annotated[int, Path(ge=1, le=2**63 - 1)]
MAX_OFFSET = 10_000


def _refs(companies: list[tuple[str, str]]) -> list[CompanyRef]:
    return [CompanyRef(role=role, name=name) for role, name in companies]


async def _detail_or_404(session: AsyncSession, recall_id: int) -> RecallDetail:
    detail = await get_recall_detail(session, recall_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Recall {recall_id} not found.")
    return detail


@router.get("", response_model=SearchResponse)
async def search(
    session: SessionDep,
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    source: Annotated[Literal["cpsc", "nhtsa"] | None, Query()] = None,
    manufacturer: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    model: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> SearchResponse:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to.")
    criteria = SearchCriteria(
        q=(q.strip() or None) if q else None,
        source=source,
        manufacturer=manufacturer,
        model=model,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    page = await search_recalls(session, criteria)
    return SearchResponse(
        items=[
            RecallSummary(
                id=hit.recall.id,
                source=hit.source,
                source_record_id=hit.recall.source_record_id,
                recall_number=hit.recall.recall_number,
                title=hit.recall.title,
                recall_date=hit.recall.recall_date,
                url=hit.recall.url,
                companies=_refs(hit.companies),
                score=hit.score,
            )
            for hit in page.hits
        ],
        total=page.total,
        limit=limit,
        offset=offset,
    )


@router.get("/{recall_id}", response_model=RecallDetailOut)
async def recall_detail(session: SessionDep, recall_id: RecallIdPath) -> RecallDetailOut:
    d = await _detail_or_404(session, recall_id)
    r = d.recall
    return RecallDetailOut(
        id=r.id,
        source=d.source.code,
        source_record_id=r.source_record_id,
        recall_number=r.recall_number,
        title=r.title,
        description=r.description,
        recall_date=r.recall_date,
        published_date=r.published_date,
        url=r.url,
        consumer_contact=r.consumer_contact,
        injuries_summary=r.injuries_summary,
        sold_at=r.sold_at,
        remedy_options=list(r.remedy_options),
        manufacturer_countries=list(r.manufacturer_countries),
        products=[
            ProductOut(
                name=p.name,
                description=p.description,
                model=p.model,
                product_type=p.product_type,
                category_code=p.category_code,
                units_text=p.units_text,
            )
            for p in r.products
        ],
        hazards=[
            HazardOut(description=h.description, hazard_type=h.hazard_type) for h in r.hazards
        ],
        remedies=[m.description for m in r.remedies],
        identifiers=[
            IdentifierOut(kind=i.kind, value=i.value, normalized_value=i.normalized_value)
            for i in r.identifiers
        ],
        companies=_refs(d.companies),
        provenance=ProvenanceOut(
            source=d.source.code,
            source_name=d.source.name,
            agency=d.source.agency,
            source_record_id=d.raw.source_record_id,
            source_url=d.raw.source_url,
            raw_record_id=d.raw.id,
            content_hash=d.raw.content_hash,
            first_seen_at=d.raw.first_seen_at,
            last_seen_at=d.raw.last_seen_at,
            normalizer_version=r.normalizer_version,
            normalized_at=r.normalized_at,
        ),
    )


@router.get("/{recall_id}/source-record", response_model=SourceRecordOut)
async def source_record(session: SessionDep, recall_id: RecallIdPath) -> SourceRecordOut:
    d = await _detail_or_404(session, recall_id)
    return SourceRecordOut(
        raw_record_id=d.raw.id,
        source=d.source.code,
        source_record_id=d.raw.source_record_id,
        source_url=d.raw.source_url,
        content_hash=d.raw.content_hash,
        first_seen_at=d.raw.first_seen_at,
        payload=d.raw.payload,
    )
