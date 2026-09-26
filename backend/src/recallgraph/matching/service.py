"""Match a user's product description against official recalls."""

import asyncio
from dataclasses import dataclass, replace

from sqlalchemy.ext.asyncio import AsyncSession

from recallgraph.matching.candidates import candidate_ids, load_profiles
from recallgraph.matching.engine import MatchQuery, MatchResult, rank, score_candidate
from recallgraph.semantic.embedder import Embedder
from recallgraph.semantic.index import nearest_recalls, similarities

SEMANTIC_NEIGHBORS = 100


@dataclass(frozen=True, slots=True)
class SemanticContext:
    """Experiment switch (Step 19): extra candidates and/or a weighted similarity signal."""

    embedder: Embedder
    add_candidates: bool = True
    weight: float = 0.0


@dataclass(frozen=True, slots=True)
class MatchOutcome:
    results: list[MatchResult]
    candidates_considered: int


def semantic_query_text(q: MatchQuery) -> str:
    return " ".join(v for v in (q.manufacturer, q.description, q.category) if v)


async def match_product(
    session: AsyncSession,
    q: MatchQuery,
    limit: int,
    semantic: SemanticContext | None = None,
) -> MatchOutcome:
    ids = await candidate_ids(session, q)
    query_text = semantic_query_text(q) if semantic else ""
    vector: list[float] | None = None
    if semantic and query_text:
        vector = (await asyncio.to_thread(semantic.embedder.embed, [query_text]))[0]
        if semantic.add_candidates:
            neighbors = await nearest_recalls(session, vector, SEMANTIC_NEIGHBORS)
            ids = list(dict.fromkeys([*ids, *(rid for rid, _ in neighbors)]))
    profiles = await load_profiles(session, ids)
    weight = semantic.weight if semantic else 0.0
    if vector is not None and weight > 0:
        sims = await similarities(session, vector, [p.recall_id for p in profiles])
        profiles = [replace(p, semantic_similarity=sims.get(p.recall_id)) for p in profiles]
    scored = [r for p in profiles if (r := score_candidate(q, p, weight)) is not None]
    return MatchOutcome(results=rank(scored, q)[:limit], candidates_considered=len(ids))
