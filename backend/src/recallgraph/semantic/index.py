"""Builds and queries the recall embedding index (pgvector, HNSW, cosine distance)."""

import asyncio
import hashlib
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from recallgraph.recalls.models import Recall, RecallProduct
from recallgraph.semantic.embedder import Embedder
from recallgraph.semantic.models import RecallEmbedding

HNSW_EF_SEARCH = 100


@dataclass(frozen=True, slots=True)
class BuildStats:
    recalls: int
    embedded: int
    unchanged: int
    duration_s: float


def product_text(title: str, products: list[str]) -> str:
    return " | ".join([title, *dict.fromkeys(p for p in products if p)])


async def build_embeddings(
    session_factory: async_sessionmaker[AsyncSession], embedder: Embedder, batch_size: int = 512
) -> BuildStats:
    """Idempotent: only recalls whose product text or model changed are (re)embedded."""
    started = time.perf_counter()
    async with session_factory() as session:
        names: dict[int, list[str]] = defaultdict(list)
        for recall_id, name, product_type in await session.execute(
            select(RecallProduct.recall_id, RecallProduct.name, RecallProduct.product_type)
        ):
            names[recall_id].extend([name, product_type or ""])
        existing = {
            rid: digest
            for rid, digest in await session.execute(
                select(RecallEmbedding.recall_id, RecallEmbedding.text_hash).where(
                    RecallEmbedding.model == embedder.model_name
                )
            )
        }
        recalls = (await session.execute(select(Recall.id, Recall.title))).all()
        todo: list[tuple[int, str, str]] = []
        for recall_id, title in recalls:
            content = product_text(title, names[recall_id])
            digest = hashlib.sha256(f"{embedder.model_name}\n{content}".encode()).hexdigest()
            if existing.get(recall_id) != digest:
                todo.append((recall_id, content, digest))

        for start in range(0, len(todo), batch_size):
            chunk = todo[start : start + batch_size]
            vectors = await asyncio.to_thread(embedder.embed, [c for _, c, _ in chunk])
            stmt = pg_insert(RecallEmbedding).values(
                [
                    {
                        "recall_id": rid,
                        "model": embedder.model_name,
                        "text_hash": digest,
                        "embedding": vector,
                    }
                    for (rid, _, digest), vector in zip(chunk, vectors, strict=True)
                ]
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[RecallEmbedding.recall_id],
                set_={
                    "model": stmt.excluded.model,
                    "text_hash": stmt.excluded.text_hash,
                    "embedding": stmt.excluded.embedding,
                },
            )
            await session.execute(stmt)
            await session.commit()
    return BuildStats(
        recalls=len(recalls),
        embedded=len(todo),
        unchanged=len(recalls) - len(todo),
        duration_s=round(time.perf_counter() - started, 3),
    )


async def nearest_recalls(
    session: AsyncSession, vector: list[float], k: int
) -> list[tuple[int, float]]:
    """(recall_id, cosine similarity) of the k nearest recalls (approximate, HNSW)."""
    await session.execute(text(f"SET LOCAL hnsw.ef_search = {max(HNSW_EF_SEARCH, k)}"))
    distance = RecallEmbedding.embedding.cosine_distance(vector)
    rows = await session.execute(
        select(RecallEmbedding.recall_id, distance).order_by(distance).limit(k)
    )
    return [(rid, round(1.0 - float(d), 4)) for rid, d in rows]


async def similarities(
    session: AsyncSession, vector: list[float], recall_ids: list[int]
) -> dict[int, float]:
    if not recall_ids:
        return {}
    distance: Any = RecallEmbedding.embedding.cosine_distance(vector)
    rows = await session.execute(
        select(RecallEmbedding.recall_id, distance).where(RecallEmbedding.recall_id.in_(recall_ids))
    )
    return {rid: round(1.0 - float(d), 4) for rid, d in rows}
