"""Grounded explanations with FAKE LLM clients (no network, no cost). SYNTHETIC records."""

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from recallgraph.explain.llm import LLMError
from recallgraph.normalization.service import normalize_cpsc_records
from tests.integration.test_normalization import _store
from tests.test_cpsc_normalizer import synthetic_payload

pytestmark = pytest.mark.integration
PASSWORD = "correct horse battery staple 42"
CREDS = {"email": "a@example.com", "password": PASSWORD}


class FakeLLM:
    model = "fake-llm"

    def __init__(self, answer: dict[str, Any] | None = None, fail: bool = False) -> None:
        self.answer = answer
        self.fail = fail
        self.prompts: list[str] = []

    async def complete_json(
        self, system: str, user: str, schema_name: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        self.prompts.append(user)
        if self.fail or self.answer is None:
            raise LLMError("synthetic outage")
        return self.answer


GOOD = {
    "summary": "Acme air fryers were recalled because they can overheat.",
    "insufficient_evidence": False,
    "points": [
        {"text": "The fryer can overheat, posing a fire hazard.", "citations": ["E6"]},
        {"text": "Stop using it and contact Acme for a refund.", "citations": ["E7"]},
    ],
}


@pytest.fixture
async def recall_id(session_factory: async_sessionmaker[AsyncSession], client: AsyncClient) -> int:
    await _store(session_factory, [synthetic_payload(RecallID=1)])
    await normalize_cpsc_records(session_factory)
    found: int = (await client.get("/api/v1/recalls", params={"model": "AF-100X"})).json()["items"][
        0
    ]["id"]
    return found


async def _auth(client: AsyncClient) -> dict[str, str]:
    await client.post("/api/v1/auth/register", json=CREDS)
    token = (await client.post("/api/v1/auth/login", json=CREDS)).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _explain(
    client: AsyncClient, app: FastAPI, recall_id: int, llm: FakeLLM | None, **body: str
) -> dict[str, Any]:
    app.state.llm = llm
    response = await client.post(
        f"/api/v1/recalls/{recall_id}/explanation", json=body, headers=await _auth(client)
    )
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


async def test_grounded_llm_answer_is_returned_with_citations(
    recall_id: int, client: AsyncClient, app: FastAPI
) -> None:
    llm = FakeLLM(GOOD)
    body = await _explain(client, app, recall_id, llm)

    assert (body["mode"], body["model"]) == ("llm", "fake-llm")
    evidence_ids = {e["id"] for e in body["evidence"]}
    assert all(set(p["citations"]) <= evidence_ids for p in body["points"])
    assert "<evidence>" in llm.prompts[0] and "[E1] (title)" in llm.prompts[0]
    assert "not a safety assessment" in body["disclaimer"]


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        ({**GOOD, "points": [{"text": "It overheats.", "citations": []}]}, "uncited point"),
        ({**GOOD, "points": [{"text": "It overheats.", "citations": ["E99"]}]}, "unknown citation"),
        ({**GOOD, "summary": "After the fix this product is safe."}, "safety claim"),
        ({**GOOD, "points": []}, "empty answer"),
    ],
)
async def test_ungrounded_answers_fall_back_to_template(
    recall_id: int, client: AsyncClient, app: FastAPI, answer: dict[str, Any], reason: str
) -> None:
    body = await _explain(client, app, recall_id, FakeLLM(answer))

    assert body["mode"] == "template"
    assert reason in body["fallback_reason"]
    assert body["points"] and all(p["citations"] for p in body["points"])


async def test_llm_outage_and_missing_key_use_template(
    recall_id: int, client: AsyncClient, app: FastAPI
) -> None:
    outage = await _explain(client, app, recall_id, FakeLLM(fail=True))
    unconfigured = await _explain(client, app, recall_id, None)

    assert outage["mode"] == unconfigured["mode"] == "template"
    assert unconfigured["fallback_reason"] == "llm_not_configured"
    assert outage["summary"].startswith("SYNTHETIC Acme Recalls Air Fryers")


async def test_question_is_passed_as_bounded_data(
    recall_id: int, client: AsyncClient, app: FastAPI
) -> None:
    llm = FakeLLM({**GOOD, "insufficient_evidence": True})
    body = await _explain(client, app, recall_id, llm, question="What will it cost in 2035?")

    assert body["insufficient_evidence"] is True
    assert "What will it cost in 2035?" in llm.prompts[0]


async def test_explanations_require_auth_and_existing_recall(
    recall_id: int, client: AsyncClient, app: FastAPI
) -> None:
    app.state.llm = FakeLLM(GOOD)
    anonymous = await client.post(f"/api/v1/recalls/{recall_id}/explanation", json={})
    headers = await _auth(client)
    missing = await client.post("/api/v1/recalls/999999999/explanation", json={}, headers=headers)
    too_long = await client.post(
        f"/api/v1/recalls/{recall_id}/explanation", json={"question": "x" * 301}, headers=headers
    )

    assert (anonymous.status_code, missing.status_code, too_long.status_code) == (401, 404, 422)
