"""Public response models for recall search and detail."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

DISCLAIMER = (
    "Results cover only the official recall datasets RecallGraph has ingested (CPSC, NHTSA). "
    "An empty result is not a safety determination: it does not mean a product is safe."
)


class CompanyRef(BaseModel):
    role: str
    name: str


class RecallSummary(BaseModel):
    id: int
    source: str
    source_record_id: str
    recall_number: str | None
    title: str
    recall_date: date | None
    url: str | None
    companies: list[CompanyRef]
    score: float | None


class SearchResponse(BaseModel):
    items: list[RecallSummary]
    total: int
    limit: int
    offset: int
    disclaimer: str = DISCLAIMER


class ProductOut(BaseModel):
    name: str
    description: str | None
    model: str | None
    product_type: str | None
    category_code: str | None
    units_text: str | None


class HazardOut(BaseModel):
    description: str
    hazard_type: str | None


class IdentifierOut(BaseModel):
    kind: str
    value: str
    normalized_value: str


class ProvenanceOut(BaseModel):
    source: str
    source_name: str
    agency: str
    source_record_id: str
    source_url: str
    raw_record_id: int
    content_hash: str
    first_seen_at: datetime
    last_seen_at: datetime
    normalizer_version: str
    normalized_at: datetime


class RecallDetailOut(BaseModel):
    id: int
    source: str
    source_record_id: str
    recall_number: str | None
    title: str
    description: str | None
    recall_date: date | None
    published_date: date | None
    url: str | None
    consumer_contact: str | None
    injuries_summary: str | None
    sold_at: str | None
    remedy_options: list[str]
    manufacturer_countries: list[str]
    products: list[ProductOut]
    hazards: list[HazardOut]
    remedies: list[str]
    identifiers: list[IdentifierOut]
    companies: list[CompanyRef]
    provenance: ProvenanceOut
    disclaimer: str = DISCLAIMER


class SourceRecordOut(BaseModel):
    """The exact authoritative payload the normalized recall was built from."""

    raw_record_id: int
    source: str
    source_record_id: str
    source_url: str
    content_hash: str
    first_seen_at: datetime
    payload: dict[str, Any]
