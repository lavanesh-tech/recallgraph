"""Grounded explanation endpoint (authenticated: LLM calls cost money)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from recallgraph.auth.dependencies import CurrentUser
from recallgraph.core.config import Settings
from recallgraph.db.session import get_session
from recallgraph.explain.llm import LLMClient, OpenAIClient
from recallgraph.explain.schemas import EvidenceOut, ExplainRequest, ExplanationOut, PointOut
from recallgraph.explain.service import PROMPT_VERSION, explain
from recallgraph.search.service import get_recall_detail

router = APIRouter(prefix="/recalls", tags=["explanations"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_llm(request: Request) -> LLMClient | None:
    override: LLMClient | None = getattr(request.app.state, "llm", None)
    if override is not None:
        return override
    settings: Settings = request.app.state.settings
    if settings.openai_api_key is None:
        return None
    return OpenAIClient(
        settings.openai_api_key.get_secret_value(), settings.openai_model, settings.openai_timeout_s
    )


@router.post("/{recall_id}/explanation", response_model=ExplanationOut)
async def explanation(
    recall_id: Annotated[int, Path(ge=1, le=2**63 - 1)],
    body: ExplainRequest,
    user: CurrentUser,
    session: SessionDep,
    llm: Annotated[LLMClient | None, Depends(get_llm)],
) -> ExplanationOut:
    detail = await get_recall_detail(session, recall_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Recall {recall_id} not found.")
    result = await explain(detail, llm, body.question)
    return ExplanationOut(
        recall_id=recall_id,
        mode=result.mode,
        model=result.model,
        prompt_version=PROMPT_VERSION,
        summary=result.summary,
        points=[PointOut(text=p.text, citations=p.citations) for p in result.points],
        insufficient_evidence=result.insufficient_evidence,
        evidence=[EvidenceOut(id=e.id, kind=e.kind, text=e.text) for e in result.evidence],
        fallback_reason=result.fallback_reason,
    )
