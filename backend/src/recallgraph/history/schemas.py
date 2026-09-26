"""Response models for safety history."""

from datetime import date

from pydantic import BaseModel

from recallgraph.search.schemas import DISCLAIMER, RecallSummary

HISTORY_DISCLAIMER = (
    "Counts cover only ingested official recall datasets and every role a company appears in "
    "(manufacturer, importer, distributor, retailer). They are not a safety rating."
)


class YearBucketOut(BaseModel):
    year: int | None
    source: str
    count: int


class TimelineResponse(BaseModel):
    total: int
    buckets: list[YearBucketOut]
    disclaimer: str = DISCLAIMER


class CompanySummary(BaseModel):
    id: int
    name: str
    normalized_name: str
    recall_count: int


class CompanySearchResponse(BaseModel):
    items: list[CompanySummary]


class RoleCount(BaseModel):
    role: str
    count: int


class CompanyHistoryResponse(BaseModel):
    id: int
    name: str
    normalized_name: str
    total_recalls: int
    first_recall_date: date | None
    last_recall_date: date | None
    by_year: list[YearBucketOut]
    by_role: list[RoleCount]
    recent_recalls: list[RecallSummary]
    disclaimer: str = HISTORY_DISCLAIMER
