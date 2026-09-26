"""Explanation API models."""

from pydantic import BaseModel, ConfigDict, Field

EXPLANATION_DISCLAIMER = (
    "AI-assisted wording of the official record shown as evidence; the official recall notice "
    "is authoritative. This explanation is not a safety assessment."
)


class ExplainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str | None = Field(default=None, min_length=1, max_length=300)


class EvidenceOut(BaseModel):
    id: str
    kind: str
    text: str


class PointOut(BaseModel):
    text: str
    citations: list[str]


class ExplanationOut(BaseModel):
    recall_id: int
    mode: str
    model: str | None
    prompt_version: str
    summary: str
    points: list[PointOut]
    insufficient_evidence: bool
    evidence: list[EvidenceOut]
    fallback_reason: str | None
    disclaimer: str = EXPLANATION_DISCLAIMER
