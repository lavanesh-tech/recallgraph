"""semantic: pgvector extension, recall_embeddings with HNSW cosine index

Revision ID: 0009_recall_embeddings
Revises: 0008_outbox
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0009_recall_embeddings"
down_revision: str | Sequence[str] | None = "0008_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "recall_embeddings",
        sa.Column("recall_id", sa.BigInteger(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["recall_id"],
            ["recalls.id"],
            name=op.f("fk_recall_embeddings_recall_id_recalls"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("recall_id", name=op.f("pk_recall_embeddings")),
    )
    op.create_index(
        "ix_recall_embeddings_hnsw",
        "recall_embeddings",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_recall_embeddings_hnsw", table_name="recall_embeddings")
    op.drop_table("recall_embeddings")
    op.execute("DROP EXTENSION IF EXISTS vector")
