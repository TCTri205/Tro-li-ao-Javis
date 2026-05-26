from __future__ import annotations

import hashlib
import logging
import os
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


class EmbeddingClient(Protocol):
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...


def get_deterministic_mock_embedding(text: str, dimension: int = 1536) -> list[float]:
    h = hashlib.md5(text.encode("utf-8")).digest()
    floats = []
    for i in range(dimension):
        byte_val = h[(i * 3) % len(h)]
        sign = -1 if i % 2 == 0 else 1
        floats.append(sign * (byte_val / 255.0))
    norm = sum(x * x for x in floats) ** 0.5
    if norm == 0:
        return [0.0] * dimension
    return [x / norm for x in floats]


class FixtureEmbeddingClient(EmbeddingClient):
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [get_deterministic_mock_embedding(text) for text in texts]


class OpenAIEmbeddingClient(EmbeddingClient):
    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        self.api_key = api_key
        self.model = model

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": texts,
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/embeddings",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
                # Extract embeddings and sort by index to guarantee ordering matches input
                results = sorted(data["data"], key=lambda x: x["index"])
                return [item["embedding"] for item in results]
        except Exception as e:
            logger.warning(f"OpenAI embedding generation failed, falling back to mock: {e}")
            return [get_deterministic_mock_embedding(text) for text in texts]


def get_embedding_client(llm_provider: str = "groq") -> EmbeddingClient:
    provider = llm_provider.lower()
    openai_key = os.getenv("OPENAI_API_KEY")
    
    if provider == "fixture":
        return FixtureEmbeddingClient()
    
    if openai_key:
        return OpenAIEmbeddingClient(api_key=openai_key)
    
    # Fallback to fixture client
    return FixtureEmbeddingClient()
