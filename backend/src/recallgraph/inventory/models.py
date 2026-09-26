"""A product a user owns (or is considering), described the same way the matcher accepts."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from recallgraph.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(description, manufacturer, model, upc) >= 1", name="has_product_info"
        ),
        CheckConstraint(
            "purchase_year IS NULL OR purchase_year BETWEEN 1950 AND 2100", name="year_range"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    nickname: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    manufacturer: Mapped[str | None] = mapped_column(String(200))
    model: Mapped[str | None] = mapped_column(String(64))
    upc: Mapped[str | None] = mapped_column(String(14))
    category: Mapped[str | None] = mapped_column(String(100))
    purchase_year: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, server_default=func.now()
    )
