"""Explainable product-to-recall matching endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from recallgraph.db.session import get_session
from recallgraph.matching.engine import ENGINE_VERSION, MatchQuery
from recallgraph.matching.schemas import MatchOut, MatchRequest, MatchResponse, SignalOut
from recallgraph.matching.service import match_product
from recallgraph.search.schemas import CompanyRef, RecallSummary

router = APIRouter(tags=["matching"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("/match", response_model=MatchResponse)
async def match(body: MatchRequest, session: SessionDep) -> MatchResponse:
    query = MatchQuery(
        description=body.description,
        manufacturer=body.manufacturer,
        model=body.model,
        upc=body.upc,
        category=body.category,
        purchase_year=body.purchase_year,
    )
    outcome = await match_product(session, query, body.limit)
    return MatchResponse(
        engine_version=ENGINE_VERSION,
        candidates_considered=outcome.candidates_considered,
        matches=[
            MatchOut(
                recall=RecallSummary(
                    id=r.profile.recall_id,
                    source=r.profile.source,
                    source_record_id=r.profile.source_record_id,
                    recall_number=r.profile.recall_number,
                    title=r.profile.title,
                    recall_date=r.profile.recall_date,
                    url=r.profile.url,
                    companies=[
                        CompanyRef(role=role, name=display)
                        for _, display, role in r.profile.companies
                    ],
                    score=r.score,
                ),
                tier=r.tier,
                score=r.score,
                signals=[
                    SignalOut(
                        name=s.name,
                        applicable=s.applicable,
                        weight=s.weight,
                        value=s.value,
                        contribution=s.contribution,
                        evidence=s.evidence,
                    )
                    for s in r.signals
                ],
            )
            for r in outcome.results
        ],
    )
