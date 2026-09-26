"""Sentence embeddings of each recall's product text (title + product names/types)."""

from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from recallgraph.db.base import Base

EMBEDDING_DIMENSIONS = 384


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RecallEmbedding(Base):
    __tablename__ = "recall_embeddings"
    __table_args__ = (
        Index(
            "ix_recall_embeddings_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    recall_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("recalls.id", ondelete="CASCADE"), primary_key=True
    )
    model: Mapped[str] = mapped_column(String(100))
    text_hash: Mapped[str] = mapped_column(String(64))
    embedding: Mapped[Any] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )
