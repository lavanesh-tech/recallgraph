"""provenance: sources, ingestion_runs, raw_records

Revision ID: 0002_provenance
Revises: 0001_baseline
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_provenance"
down_revision: str | Sequence[str] | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("agency", sa.String(length=200), nullable=False),
        sa.Column("homepage_url", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sources")),
        sa.UniqueConstraint("code", name=op.f("uq_sources_code")),
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("pipeline_version", sa.String(length=64), nullable=False),
        sa.Column(
            "parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("records_seen", sa.Integer(), server_default="0", nullable=False),
        sa.Column("records_inserted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("records_unchanged", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name=op.f("ck_ingestion_runs_status_valid"),
        ),
        sa.CheckConstraint(
            "records_inserted + records_unchanged <= records_seen",
            name=op.f("ck_ingestion_runs_counts_consistent"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_ingestion_runs_source_id_sources"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingestion_runs")),
    )
    op.create_index(
        "ix_ingestion_runs_source_started", "ingestion_runs", ["source_id", "started_at"]
    )
    op.create_table(
        "raw_records",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("source_record_id", sa.String(length=200), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("first_seen_run_id", sa.Uuid(), nullable=False),
        sa.Column("last_seen_run_id", sa.Uuid(), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "char_length(content_hash) = 64", name=op.f("ck_raw_records_content_hash_sha256")
        ),
        sa.ForeignKeyConstraint(
            ["first_seen_run_id"],
            ["ingestion_runs.id"],
            name=op.f("fk_raw_records_first_seen_run_id_ingestion_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["last_seen_run_id"],
            ["ingestion_runs.id"],
            name=op.f("fk_raw_records_last_seen_run_id_ingestion_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_raw_records_source_id_sources"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_raw_records")),
        sa.UniqueConstraint(
            "source_id",
            "source_record_id",
            "content_hash",
            name="uq_raw_records_source_record_hash",
        ),
    )


def downgrade() -> None:
    op.drop_table("raw_records")
    op.drop_index("ix_ingestion_runs_source_started", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
    op.drop_table("sources")
