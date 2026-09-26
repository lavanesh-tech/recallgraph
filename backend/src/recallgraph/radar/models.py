"""Radar alerts (one per inventory item x recall, idempotent) and radar run bookkeeping."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from recallgraph.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RadarAlert(Base):
    __tablename__ = "radar_alerts"
    __table_args__ = (
        UniqueConstraint("inventory_item_id", "recall_id", name="uq_radar_alerts_item_recall"),
        Index("ix_radar_alerts_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    inventory_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inventory_items.id", ondelete="CASCADE")
    )
    recall_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("recalls.id", ondelete="CASCADE"), index=True
    )
    tier: Mapped[str] = mapped_column(String(32))
    score: Mapped[float] = mapped_column(Float)
    engine_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RadarRun(Base):
    __tablename__ = "radar_runs"
    __table_args__ = (
        CheckConstraint("status IN ('succeeded', 'failed')", name="status_valid"),
        Index("ix_radar_runs_started_at", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16))
    recall_watermark: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    item_watermark: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recalls_scanned: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    items_scanned: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    alerts_created: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text)
