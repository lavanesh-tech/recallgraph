"""Request/response models for product matching."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from recallgraph.search.schemas import RecallSummary

MATCH_DISCLAIMER = (
    "Scores are deterministic similarity measures, not confirmation that your product is "
    "recalled: check the model, lot and date details on the official notice. A missing match "
    "does not mean the product is safe; it only means no ingested recall matched."
)


class MatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    description: str | None = Field(default=None, min_length=1, max_length=500)
    manufacturer: str | None = Field(default=None, min_length=1, max_length=200)
    model: str | None = Field(default=None, min_length=1, max_length=64)
    upc: str | None = Field(default=None, pattern=r"^\d{8,14}$")
    category: str | None = Field(default=None, min_length=1, max_length=100)
    purchase_year: int | None = Field(default=None, ge=1950, le=2100)
    limit: int = Field(default=10, ge=1, le=50)

    @model_validator(mode="after")
    def _needs_product_information(self) -> Self:
        if not any((self.description, self.manufacturer, self.model, self.upc)):
            raise ValueError("provide at least one of description, manufacturer, model or upc")
        return self


class SignalOut(BaseModel):
    name: str
    applicable: bool
    weight: float
    value: float
    contribution: float
    evidence: str


class MatchOut(BaseModel):
    recall: RecallSummary
    tier: str
    score: float
    signals: list[SignalOut]


class MatchResponse(BaseModel):
    engine_version: str
    candidates_considered: int
    matches: list[MatchOut]
    disclaimer: str = MATCH_DISCLAIMER
