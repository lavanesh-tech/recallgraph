"""Candidate generation (deterministic SQL) and profile loading for the matching engine."""

from collections import defaultdict
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from recallgraph.matching.engine import CandidateProfile, MatchQuery, query_terms, title_tokens
from recallgraph.matching.text import tokenize
from recallgraph.normalization.text import normalize_company_name, normalize_identifier
from recallgraph.provenance.models import Source
from recallgraph.recalls.models import (
    Company,
    Recall,
    RecallCompany,
    RecallIdentifier,
    RecallProduct,
)
from recallgraph.search.service import _TS_CONFIG

CHANNEL_LIMIT = 200
FAMILY_MIN_LENGTH = 4


async def candidate_ids(session: AsyncSession, q: MatchQuery) -> list[int]:
    """Union of three retrieval channels: identifiers, manufacturer, full-text terms."""
    found: dict[int, None] = {}

    keys = [k for k in (normalize_identifier(v) for v in (q.model, q.upc) if v) if k]
    for key in keys:
        cond: ColumnElement[bool] = RecallIdentifier.normalized_value == key
        if len(key) >= FAMILY_MIN_LENGTH:
            cond = cond | RecallIdentifier.normalized_value.startswith(key, autoescape=True)
        rows = await session.execute(
            select(RecallIdentifier.recall_id).where(cond).limit(CHANNEL_LIMIT)
        )
        found.update(dict.fromkeys(rows.scalars()))

    company_key = normalize_company_name(q.manufacturer) if q.manufacturer else None
    if company_key:
        # Whole-token match: 'ford' matches 'ford motor' but not 'northford'.
        pattern = f"(^| ){company_key}( |$)"
        rows = await session.execute(
            select(Recall.id)
            .join(RecallCompany, RecallCompany.recall_id == Recall.id)
            .join(Company, Company.id == RecallCompany.company_id)
            .where(Company.normalized_name.regexp_match(pattern))
            .order_by(Recall.recall_date.desc().nulls_last(), Recall.id.desc())
            .limit(CHANNEL_LIMIT)
        )
        found.update(dict.fromkeys(rows.scalars()))

    terms = query_terms(q)
    if terms:
        tsquery = func.to_tsquery(_TS_CONFIG, " | ".join(terms))
        rows = await session.execute(
            select(Recall.id)
            .where(Recall.search_vector.op("@@")(tsquery))
            .order_by(func.ts_rank_cd(Recall.search_vector, tsquery).desc(), Recall.id.desc())
            .limit(CHANNEL_LIMIT)
        )
        found.update(dict.fromkeys(rows.scalars()))
    return list(found)


async def load_profiles(session: AsyncSession, ids: list[int]) -> list[CandidateProfile]:
    if not ids:
        return []
    texts: dict[int, list[str]] = defaultdict(list)
    idents: dict[int, list[tuple[str, str, str]]] = defaultdict(list)
    companies: dict[int, list[tuple[str, str, str]]] = defaultdict(list)

    products = await session.execute(
        select(RecallProduct.recall_id, RecallProduct.name, RecallProduct.product_type).where(
            RecallProduct.recall_id.in_(ids)
        )
    )
    for recall_id, name, product_type in products:
        texts[recall_id].extend([name, product_type or ""])
    identifier_rows = await session.execute(
        select(
            RecallIdentifier.recall_id,
            RecallIdentifier.kind,
            RecallIdentifier.value,
            RecallIdentifier.normalized_value,
        ).where(RecallIdentifier.recall_id.in_(ids))
    )
    for recall_id, kind, value, norm in identifier_rows:
        idents[recall_id].append((kind, value, norm))
    company_rows = await session.execute(
        select(
            RecallCompany.recall_id,
            Company.normalized_name,
            Company.display_name,
            RecallCompany.role,
        )
        .join(Company, Company.id == RecallCompany.company_id)
        .where(RecallCompany.recall_id.in_(ids))
        .order_by(RecallCompany.id)
    )
    for recall_id, norm, display, role in company_rows:
        companies[recall_id].append((norm, display, role))

    recalls = await session.execute(
        select(
            Recall.id,
            Source.code,
            Recall.source_record_id,
            Recall.recall_number,
            Recall.title,
            Recall.description,
            Recall.recall_date,
            Recall.url,
        )
        .join(Source, Source.id == Recall.source_id)
        .where(Recall.id.in_(ids))
    )
    profiles: list[CandidateProfile] = []
    for rid, source, sid, number, title, description, recall_date, url in recalls:
        text: list[Any] = [title, description or "", *texts[rid]]
        profiles.append(
            CandidateProfile(
                recall_id=rid,
                source=source,
                source_record_id=sid,
                recall_number=number,
                title=title,
                recall_date=recall_date,
                url=url,
                text_tokens=frozenset(tokenize(" ".join(text))),
                title_tokens=title_tokens(title),
                identifiers=tuple(idents[rid]),
                companies=tuple(companies[rid]),
            )
        )
    return profiles
