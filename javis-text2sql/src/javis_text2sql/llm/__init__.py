from __future__ import annotations

from typing import TYPE_CHECKING
from javis_text2sql.llm.client import LLMClient
from javis_text2sql.llm.fixture import FixtureLLMClient
from javis_text2sql.llm.groq import GroqClient
from javis_text2sql.llm.embeddings import EmbeddingClient, get_embedding_client

if TYPE_CHECKING:
    from javis_text2sql.config import Settings


def get_llm_client(settings: Settings) -> LLMClient:
    provider = settings.llm_provider.lower()
    if provider == "fixture":
        return FixtureLLMClient()
    elif provider == "groq":
        if not settings.groq_api_keys:
            raise ValueError(
                "Groq API keys are not configured. Please set GROQ_API_KEYS (comma-separated), "
                "GROQ_API_KEY, or GROQ_API_KEY_1, GROQ_API_KEY_2 in your environment."
            )
        return GroqClient(
            api_keys=settings.groq_api_keys,
            model=settings.groq_model,
        )
    else:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")
