from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from .llm_client import LLMClient, SchemaT

logger = logging.getLogger(__name__)


class GroqClient(LLMClient):
    def __init__(
        self,
        api_keys: list[str],
        model: str = "llama-3.3-70b-versatile",
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> None:
        if not api_keys:
            raise ValueError("At least one Groq API key must be provided")
        self.api_keys = [k.strip() for k in api_keys if k.strip()]
        if not self.api_keys:
            raise ValueError("At least one non-empty Groq API key must be provided")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._current_index = 0
        self._lock = asyncio.Lock()

    async def _get_next_api_key(self) -> str:
        async with self._lock:
            key = self.api_keys[self._current_index]
            self._current_index = (self._current_index + 1) % len(self.api_keys)
            return key

    async def _request_with_rotation(
        self, messages: list[dict[str, str]], response_format: dict[str, Any] | None = None
    ) -> str:
        num_keys = len(self.api_keys)
        last_exception: Exception | None = None

        for _ in range(num_keys):
            api_key = await self._get_next_api_key()
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            }
            if response_format:
                payload["response_format"] = response_format

            key_display = f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 10 else "invalid_key"
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        json=payload,
                        headers=headers,
                    )

                    if response.status_code == 429:
                        logger.warning(
                            "Groq API key (%s) returned 429 Rate Limit. Rotating to next key.",
                            key_display,
                        )
                        continue

                    response.raise_for_status()
                    data = response.json()
                    return str(data["choices"][0]["message"]["content"])
            except Exception as exc:
                logger.warning("Groq request failed with key (%s): %s", key_display, exc)
                last_exception = exc
                continue

        raise RuntimeError(f"All {num_keys} Groq API keys failed. Last error: {last_exception}")

    async def structured_output(self, system: str, user: str, schema: type[SchemaT]) -> SchemaT:
        schema_json = json.dumps(schema.model_json_schema())
        modified_system = (
            f"{system}\n\n"
            "You must return a valid JSON object strictly matching this JSON Schema:\n"
            f"{schema_json}\n\n"
            "Do not include any extra explanation or markdown block."
        )
        messages = [
            {"role": "system", "content": modified_system},
            {"role": "user", "content": user},
        ]
        content = await self._request_with_rotation(messages, response_format={"type": "json_object"})
        parsed = json.loads(content)
        return schema.model_validate(parsed)

    async def generate(self, system: str, user: str) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return await self._request_with_rotation(messages)
