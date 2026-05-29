from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from javis_text2sql.llm.client import LLMClient, SchemaT

logger = logging.getLogger(__name__)


class GeminiClient(LLMClient):
    def __init__(
        self,
        api_keys: list[str],
        model: str = "gemini-2.5-flash",
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> None:
        if not api_keys:
            raise ValueError("At least one Gemini API key must be provided")
        self.api_keys = [k.strip() for k in api_keys if k.strip()]
        if not self.api_keys:
            raise ValueError("At least one non-empty Gemini API key must be provided")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        # Index for round-robin rotation
        self._current_index = 0
        self._lock = asyncio.Lock()

    async def _get_next_api_key(self) -> str:
        async with self._lock:
            key = self.api_keys[self._current_index]
            self._current_index = (self._current_index + 1) % len(self.api_keys)
            return key

    async def _request(
        self, messages: list[dict[str, str]], response_format: dict[str, Any] | None = None
    ) -> str:
        num_keys = len(self.api_keys)
        last_exception: Exception | None = None
        
        # Allow up to 3 full rotations of keys
        max_attempts = num_keys * 3

        for attempt in range(max_attempts):
            api_key = await self._get_next_api_key()
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            }
            if response_format:
                payload["response_format"] = response_format

            key_display = f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 10 else "invalid_key"
            logger.info(f"Sending request to Gemini ({self.model}) with key {key_display}")

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                        json=payload,
                        headers=headers,
                    )
                    
                    if response.status_code == 429:
                        logger.warning(
                            f"Gemini API key ({key_display}) returned 429 Rate Limit. Rotating to next key."
                        )
                        # If a full rotation has failed with 429, back off to reset the limit window
                        if (attempt + 1) % num_keys == 0:
                            sleep_time = 5 * ((attempt + 1) // num_keys)
                            logger.warning(f"All Gemini keys rate limited. Sleeping for {sleep_time}s before retrying...")
                            await asyncio.sleep(sleep_time)
                        continue
                    
                    response.raise_for_status()
                    data = response.json()
                    return str(data["choices"][0]["message"]["content"])
            except Exception as e:
                logger.warning(
                    f"Gemini request failed with key ({key_display}): {e}. Retrying with next key if available."
                )
                last_exception = e
                if (attempt + 1) % num_keys == 0:
                    sleep_time = 3 * ((attempt + 1) // num_keys)
                    await asyncio.sleep(sleep_time)
                continue

        raise RuntimeError(
            f"All {num_keys} Gemini API keys failed after {max_attempts} attempts. Last error: {last_exception}"
        )

    async def structured_output(self, system: str, user: str, schema: type[SchemaT]) -> SchemaT:
        schema_json = json.dumps(schema.model_json_schema())
        modified_system = (
            f"{system}\n\n"
            f"You must return a valid JSON object strictly matching this JSON Schema:\n"
            f"{schema_json}\n\n"
            f"Do not include any extra explanation or markdown block (like ```json). Just the raw JSON object."
        )
        messages = [
            {"role": "system", "content": modified_system},
            {"role": "user", "content": user},
        ]
        content = await self._request(messages, response_format={"type": "json_object"})
        
        parsed = json.loads(content)
        return schema.model_validate(parsed)

    async def generate(self, system: str, user: str) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return await self._request(messages)
