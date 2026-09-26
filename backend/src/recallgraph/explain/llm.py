"""LLM client abstraction. Production uses OpenAI; tests use deterministic fakes."""

import json
from typing import Any, Protocol

from openai import AsyncOpenAI


class LLMError(Exception):
    pass


class LLMClient(Protocol):
    model: str

    async def complete_json(
        self, system: str, user: str, schema_name: str, schema: dict[str, Any]
    ) -> dict[str, Any]: ...


class OpenAIClient:
    def __init__(self, api_key: str, model: str, timeout_s: float) -> None:
        self.model = model
        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout_s, max_retries=2)

    async def complete_json(
        self, system: str, user: str, schema_name: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                temperature=0,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": schema_name, "schema": schema, "strict": True},
                },
            )
            content = response.choices[0].message.content or ""
            data = json.loads(content)
        except Exception as exc:  # network, API, refusal or malformed JSON: caller falls back
            raise LLMError(type(exc).__name__) from exc
        if not isinstance(data, dict):
            raise LLMError("non-object JSON")
        return data
