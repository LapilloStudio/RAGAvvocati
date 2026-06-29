"""Pluggable embedding providers.

The pipeline depends only on the `EmbeddingProvider` interface, so the model/vendor can
be swapped (managed API ↔ self-hosted bge-m3 ↔ deterministic fake for tests) without
touching ingestion or retrieval. The vector dimension MUST match the vector(N) column
in the database (settings.embeddings_dimension).
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod

import httpx

from app.core.config import Settings, get_settings


class EmbeddingProvider(ABC):
    """Embed text into fixed-size vectors."""

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_batch([text]))[0]


class ManagedEmbeddingProvider(EmbeddingProvider):
    """Calls an OpenAI-compatible embeddings endpoint (no-retention recommended).

    Works with any provider exposing `POST {base}/embeddings`. Swap the base/model in
    config to point at an EU-hosted or self-hosted gateway.
    """

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings.embeddings_dimension)
        self._base = settings.embeddings_api_base.rstrip("/")
        self._key = settings.embeddings_api_key
        self._model = settings.embeddings_model

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self._base}/embeddings",
                headers={"Authorization": f"Bearer {self._key}"},
                json={"model": self._model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()["data"]
        # Preserve input order.
        return [item["embedding"] for item in sorted(data, key=lambda d: d["index"])]


class FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic, network-free embeddings for tests and local smoke runs.

    Hashes the text into a stable pseudo-vector. Good enough to exercise storage,
    the RPC, and RLS isolation without an external dependency.
    """

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def _embed(self, text: str) -> list[float]:
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        # Stretch the 32-byte digest to `dimension` floats in [-1, 1].
        return [
            (seed[i % len(seed)] / 127.5) - 1.0 for i in range(self.dimension)
        ]


def get_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    settings = settings or get_settings()
    provider = settings.embeddings_provider.lower()
    if provider == "fake":
        return FakeEmbeddingProvider(settings.embeddings_dimension)
    if provider in ("managed", "selfhosted"):
        return ManagedEmbeddingProvider(settings)
    raise ValueError(f"Unknown EMBEDDINGS_PROVIDER: {settings.embeddings_provider!r}")
