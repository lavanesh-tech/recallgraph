"""recall search: pg_trgm, generated weighted tsvector, GIN indexes

Revision ID: 0004_recall_search
Revises: 0003_recall_domain
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_recall_search"
down_revision: str | Sequence[str] | None = "0003_recall_domain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEARCH_VECTOR_SQL = (
    "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(description, '')), 'B')"
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.add_column(
        "recalls",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(SEARCH_VECTOR_SQL, persisted=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_recalls_search_vector", "recalls", ["search_vector"], postgresql_using="gin"
    )
    op.create_index(
        "ix_recalls_title_trgm",
        "recalls",
        ["title"],
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_recalls_title_trgm", table_name="recalls")
    op.drop_index("ix_recalls_search_vector", table_name="recalls")
    op.drop_column("recalls", "search_vector")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
