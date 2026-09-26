"""recall domain: recalls, products, hazards, remedies, identifiers, companies

Revision ID: 0003_recall_domain
Revises: 0002_provenance
Create Date: 2026-09-26
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_recall_domain"
down_revision: str | Sequence[str] | None = "0002_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _pk_id(table: str) -> list[Any]:
    return [
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
    ]


def _recall_fk(table: str) -> list[Any]:
    return [
        sa.Column("recall_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["recall_id"],
            ["recalls.id"],
            name=op.f(f"fk_{table}_recall_id_recalls"),
            ondelete="CASCADE",
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companies")),
        sa.UniqueConstraint("normalized_name", name=op.f("uq_companies_normalized_name")),
    )
    op.create_table(
        "recalls",
        *_pk_id("recalls"),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("source_record_id", sa.String(length=200), nullable=False),
        sa.Column("raw_record_id", sa.BigInteger(), nullable=False),
        sa.Column("normalizer_version", sa.String(length=32), nullable=False),
        sa.Column("recall_number", sa.String(length=64), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("recall_date", sa.Date(), nullable=True),
        sa.Column("published_date", sa.Date(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("consumer_contact", sa.Text(), nullable=True),
        sa.Column("injuries_summary", sa.Text(), nullable=True),
        sa.Column("sold_at", sa.Text(), nullable=True),
        sa.Column(
            "remedy_options",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "manufacturer_countries",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "normalized_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["raw_record_id"],
            ["raw_records.id"],
            name=op.f("fk_recalls_raw_record_id_raw_records"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_recalls_source_id_sources"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("source_id", "source_record_id", name="uq_recalls_source_record"),
    )
    op.create_index(op.f("ix_recalls_raw_record_id"), "recalls", ["raw_record_id"])
    op.create_index(op.f("ix_recalls_recall_date"), "recalls", ["recall_date"])

    op.create_table(
        "recall_products",
        *_pk_id("recall_products"),
        *_recall_fk("recall_products"),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("product_type", sa.Text(), nullable=True),
        sa.Column("category_code", sa.String(length=32), nullable=True),
        sa.Column("units_text", sa.Text(), nullable=True),
    )
    op.create_index(op.f("ix_recall_products_recall_id"), "recall_products", ["recall_id"])

    op.create_table(
        "recall_hazards",
        *_pk_id("recall_hazards"),
        *_recall_fk("recall_hazards"),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("hazard_type", sa.Text(), nullable=True),
    )
    op.create_index(op.f("ix_recall_hazards_recall_id"), "recall_hazards", ["recall_id"])

    op.create_table(
        "recall_remedies",
        *_pk_id("recall_remedies"),
        *_recall_fk("recall_remedies"),
        sa.Column("description", sa.Text(), nullable=False),
    )
    op.create_index(op.f("ix_recall_remedies_recall_id"), "recall_remedies", ["recall_id"])

    op.create_table(
        "recall_identifiers",
        *_pk_id("recall_identifiers"),
        *_recall_fk("recall_identifiers"),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("normalized_value", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "kind IN ('upc', 'model', 'model_text')", name=op.f("ck_recall_identifiers_kind_valid")
        ),
    )
    op.create_index(
        op.f("ix_recall_identifiers_normalized_value"), "recall_identifiers", ["normalized_value"]
    )
    op.create_index(op.f("ix_recall_identifiers_recall_id"), "recall_identifiers", ["recall_id"])

    op.create_table(
        "recall_companies",
        *_pk_id("recall_companies"),
        *_recall_fk("recall_companies"),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("raw_name", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "role IN ('manufacturer', 'importer', 'distributor', 'retailer')",
            name=op.f("ck_recall_companies_role_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_recall_companies_company_id_companies"),
            ondelete="RESTRICT",
        ),
    )
    op.create_index(op.f("ix_recall_companies_company_id"), "recall_companies", ["company_id"])
    op.create_index(op.f("ix_recall_companies_recall_id"), "recall_companies", ["recall_id"])


def downgrade() -> None:
    for table in (
        "recall_companies",
        "recall_identifiers",
        "recall_remedies",
        "recall_hazards",
        "recall_products",
        "recalls",
        "companies",
    ):
        op.drop_table(table)
