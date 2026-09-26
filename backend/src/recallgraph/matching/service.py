"""Match a user's product description against official recalls."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from recallgraph.matching.candidates import candidate_ids, load_profiles
from recallgraph.matching.engine import MatchQuery, MatchResult, rank, score_candidate


@dataclass(frozen=True, slots=True)
class MatchOutcome:
    results: list[MatchResult]
    candidates_considered: int


async def match_product(session: AsyncSession, q: MatchQuery, limit: int) -> MatchOutcome:
    ids = await candidate_ids(session, q)
    profiles = await load_profiles(session, ids)
    scored = [r for p in profiles if (r := score_candidate(q, p)) is not None]
    return MatchOutcome(results=rank(scored)[:limit], candidates_considered=len(ids))
