"""inventory: per-user saved products

Revision ID: 0006_inventory
Revises: 0005_auth
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_inventory"
down_revision: str | Sequence[str] | None = "0005_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inventory_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("nickname", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("manufacturer", sa.String(length=200), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("upc", sa.String(length=14), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("purchase_year", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "num_nonnulls(description, manufacturer, model, upc) >= 1",
            name=op.f("ck_inventory_items_has_product_info"),
        ),
        sa.CheckConstraint(
            "purchase_year IS NULL OR purchase_year BETWEEN 1950 AND 2100",
            name=op.f("ck_inventory_items_year_range"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_inventory_items_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_items")),
    )
    op.create_index(op.f("ix_inventory_items_user_id"), "inventory_items", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_inventory_items_user_id"), table_name="inventory_items")
    op.drop_table("inventory_items")
