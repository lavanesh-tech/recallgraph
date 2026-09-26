"""Normalized recall domain. Every recall links to the exact raw record version it came from."""

from datetime import UTC, date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from recallgraph.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Company(Base):
    """A firm named in recalls, deduplicated by a normalized name key."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    normalized_name: Mapped[str] = mapped_column(Text, unique=True)
    display_name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )


class RecallProduct(Base):
    __tablename__ = "recall_products"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    recall_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("recalls.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    product_type: Mapped[str | None] = mapped_column(Text)
    category_code: Mapped[str | None] = mapped_column(String(32))
    units_text: Mapped[str | None] = mapped_column(Text)


class RecallHazard(Base):
    __tablename__ = "recall_hazards"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    recall_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("recalls.id", ondelete="CASCADE"), index=True
    )
    description: Mapped[str] = mapped_column(Text)
    hazard_type: Mapped[str | None] = mapped_column(Text)


class RecallRemedy(Base):
    __tablename__ = "recall_remedies"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    recall_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("recalls.id", ondelete="CASCADE"), index=True
    )
    description: Mapped[str] = mapped_column(Text)


class RecallIdentifier(Base):
    """Model numbers / UPCs. normalized_value (uppercase alphanumerics) is the matching key."""

    __tablename__ = "recall_identifiers"
    __table_args__ = (CheckConstraint("kind IN ('upc', 'model', 'model_text')", name="kind_valid"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    recall_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("recalls.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    value: Mapped[str] = mapped_column(Text)
    normalized_value: Mapped[str] = mapped_column(String(64), index=True)


class RecallCompany(Base):
    __tablename__ = "recall_companies"
    __table_args__ = (
        CheckConstraint(
            "role IN ('manufacturer', 'importer', 'distributor', 'retailer')", name="role_valid"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    recall_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("recalls.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    raw_name: Mapped[str] = mapped_column(Text)


class Recall(Base):
    __tablename__ = "recalls"
    __table_args__ = (
        UniqueConstraint("source_id", "source_record_id", name="uq_recalls_source_record"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="RESTRICT"))
    source_record_id: Mapped[str] = mapped_column(String(200))
    raw_record_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("raw_records.id", ondelete="RESTRICT"), index=True
    )
    normalizer_version: Mapped[str] = mapped_column(String(32))
    recall_number: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    recall_date: Mapped[date | None] = mapped_column(Date, index=True)
    published_date: Mapped[date | None] = mapped_column(Date)
    url: Mapped[str | None] = mapped_column(Text)
    consumer_contact: Mapped[str | None] = mapped_column(Text)
    injuries_summary: Mapped[str | None] = mapped_column(Text)
    sold_at: Mapped[str | None] = mapped_column(Text)
    remedy_options: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default=text("'{}'")
    )
    manufacturer_countries: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default=text("'{}'")
    )
    normalized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )

    # lazy="raise": async code must load children explicitly (no hidden I/O).
    products: Mapped[list[RecallProduct]] = relationship(
        cascade="all, delete-orphan", lazy="raise", order_by=RecallProduct.id
    )
    hazards: Mapped[list[RecallHazard]] = relationship(
        cascade="all, delete-orphan", lazy="raise", order_by=RecallHazard.id
    )
    remedies: Mapped[list[RecallRemedy]] = relationship(
        cascade="all, delete-orphan", lazy="raise", order_by=RecallRemedy.id
    )
    identifiers: Mapped[list[RecallIdentifier]] = relationship(
        cascade="all, delete-orphan", lazy="raise", order_by=RecallIdentifier.id
    )
    companies: Mapped[list[RecallCompany]] = relationship(
        cascade="all, delete-orphan", lazy="raise", order_by=RecallCompany.id
    )
