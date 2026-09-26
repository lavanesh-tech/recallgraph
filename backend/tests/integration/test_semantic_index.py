"""pgvector index + semantic matching wiring with a deterministic FAKE embedder (no download)."""

import math
import zlib
from collections.abc import Sequence

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from recallgraph.matching.engine import MatchQuery
from recallgraph.matching.service import SemanticContext, match_product
from recallgraph.normalization.service import normalize_cpsc_records
from recallgraph.semantic.index import build_embeddings, nearest_recalls
from tests.integration.test_normalization import _store
from tests.integration.test_search_api import HEATER
from tests.test_cpsc_normalizer import synthetic_payload

pytestmark = pytest.mark.integration


class FakeEmbedder:
    """Hashed bag-of-words vectors: deterministic, 384 dims, unit length."""

    model_name = "fake-bow-384"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            v = [0.0] * 384
            v[0] = 0.01
            for token in text.lower().split():
                v[zlib.crc32(token.strip("|,.").encode()) % 383 + 1] += 1.0
            norm = math.sqrt(sum(x * x for x in v))
            vectors.append([x / norm for x in v])
        return vectors


@pytest.fixture
async def catalog(session_factory: async_sessionmaker[AsyncSession]) -> None:
    await _store(session_factory, [synthetic_payload(RecallID=1), HEATER])
    await normalize_cpsc_records(session_factory)


async def test_build_is_idempotent_and_neighbors_are_ranked(
    catalog: None, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    embedder = FakeEmbedder()
    first = await build_embeddings(session_factory, embedder)
    second = await build_embeddings(session_factory, embedder)

    assert (first.recalls, first.embedded, second.embedded, second.unchanged) == (2, 2, 0, 2)
    async with session_factory() as session:
        neighbors = await nearest_recalls(session, embedder.embed(["acme air fryers"])[0], 2)
    assert len(neighbors) == 2
    assert neighbors[0][1] > neighbors[1][1]


async def test_semantic_channel_adds_candidates_lexical_retrieval_cannot_find(
    catalog: None, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    embedder = FakeEmbedder()
    await build_embeddings(session_factory, embedder)
    query = MatchQuery(description="qqqzzz")  # no lexical overlap with anything

    async with session_factory() as session:
        plain = await match_product(session, query, 10)
        semantic = await match_product(
            session, query, 10, SemanticContext(embedder=embedder, weight=0.15)
        )

    assert (plain.candidates_considered, semantic.candidates_considered) == (0, 2)
