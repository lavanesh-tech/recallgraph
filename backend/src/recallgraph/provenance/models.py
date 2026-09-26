"""Provenance model: which agency supplied each raw record, when, and in which ingestion run."""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from recallgraph.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class IngestionRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Source(Base):
    """An authoritative data provider (e.g. CPSC recalls API)."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    agency: Mapped[str] = mapped_column(String(200))
    homepage_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )


class IngestionRun(Base):
    """One execution of a source adapter: parameters, code version, outcome and counts."""

    __tablename__ = "ingestion_runs"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'succeeded', 'failed')", name="status_valid"),
        CheckConstraint(
            "records_inserted + records_unchanged <= records_seen", name="counts_consistent"
        ),
        Index("ix_ingestion_runs_source_started", "source_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(16))
    pipeline_version: Mapped[str] = mapped_column(String(64))
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    records_seen: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    records_inserted: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    records_unchanged: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text)


class RawRecord(Base):
    """An exact source payload version. A changed payload is stored as a new version."""

    __tablename__ = "raw_records"
    __table_args__ = (
        # Idempotency key. Its (source_id, source_record_id) prefix also serves record lookups.
        UniqueConstraint(
            "source_id",
            "source_record_id",
            "content_hash",
            name="uq_raw_records_source_record_hash",
        ),
        CheckConstraint("char_length(content_hash) = 64", name="content_hash_sha256"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="RESTRICT"))
    source_record_id: Mapped[str] = mapped_column(String(200))
    content_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    source_url: Mapped[str] = mapped_column(Text)
    first_seen_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingestion_runs.id", ondelete="RESTRICT")
    )
    last_seen_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingestion_runs.id", ondelete="RESTRICT")
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )
