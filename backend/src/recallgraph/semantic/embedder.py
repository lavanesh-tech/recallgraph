"""Embedding models. Local ONNX model via fastembed: no API key, no per-call cost."""

from collections.abc import Sequence
from typing import Any, Protocol


class Embedder(Protocol):
    model_name: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class FastEmbedder:
    """sentence-transformers/all-MiniLM-L6-v2 (384 dims), downloaded once and cached."""

    model_name = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self) -> None:
        from fastembed import TextEmbedding

        self._model: Any = TextEmbedding(model_name=self.model_name)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(x) for x in vector] for vector in self._model.embed(list(texts))]
