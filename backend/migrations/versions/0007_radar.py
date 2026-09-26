"""radar: radar_alerts, radar_runs

Revision ID: 0007_radar
Revises: 0006_inventory
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_radar"
down_revision: str | Sequence[str] | None = "0006_inventory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "radar_alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("inventory_item_id", sa.Uuid(), nullable=False),
        sa.Column("recall_id", sa.BigInteger(), nullable=False),
        sa.Column("tier", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("engine_version", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["inventory_item_id"],
            ["inventory_items.id"],
            name=op.f("fk_radar_alerts_inventory_item_id_inventory_items"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recall_id"],
            ["recalls.id"],
            name=op.f("fk_radar_alerts_recall_id_recalls"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_radar_alerts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_radar_alerts")),
        sa.UniqueConstraint("inventory_item_id", "recall_id", name="uq_radar_alerts_item_recall"),
    )
    op.create_index(op.f("ix_radar_alerts_recall_id"), "radar_alerts", ["recall_id"])
    op.create_index("ix_radar_alerts_user_created", "radar_alerts", ["user_id", "created_at"])
    op.create_table(
        "radar_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("recall_watermark", sa.DateTime(timezone=True), nullable=True),
        sa.Column("item_watermark", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recalls_scanned", sa.Integer(), server_default="0", nullable=False),
        sa.Column("items_scanned", sa.Integer(), server_default="0", nullable=False),
        sa.Column("alerts_created", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed')", name=op.f("ck_radar_runs_status_valid")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_radar_runs")),
    )
    op.create_index("ix_radar_runs_started_at", "radar_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_radar_runs_started_at", table_name="radar_runs")
    op.drop_table("radar_runs")
    op.drop_index("ix_radar_alerts_user_created", table_name="radar_alerts")
    op.drop_index(op.f("ix_radar_alerts_recall_id"), table_name="radar_alerts")
    op.drop_table("radar_alerts")
