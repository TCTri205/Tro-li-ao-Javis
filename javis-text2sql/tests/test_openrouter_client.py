from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from javis_text2sql.config import Settings
from javis_text2sql.llm import get_llm_client
from javis_text2sql.llm.openrouter import OpenRouterClient


class DummySchema(BaseModel):
    name: str
    age: int


@pytest.mark.asyncio
async def test_openrouter_client_success() -> None:
    client = OpenRouterClient(api_keys=["key1", "key2"], model="deepseek/deepseek-chat")
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Hello OpenRouter"
                }
            }
        ]
    }
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
        result = await client.generate("system_prompt", "user_prompt")
        assert result == "Hello OpenRouter"
        assert mock_post.call_count == 1
        headers = mock_post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer key1"
        assert mock_post.call_args[0][0] == "https://openrouter.ai/api/v1/chat/completions"


@pytest.mark.asyncio
async def test_openrouter_client_round_robin() -> None:
    client = OpenRouterClient(api_keys=["key1", "key2"], model="deepseek/deepseek-chat")
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Hello"}}]
    }
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
        await client.generate("sys", "user")
        assert mock_post.call_args_list[0][1]["headers"]["Authorization"] == "Bearer key1"
        
        await client.generate("sys", "user")
        assert mock_post.call_args_list[1][1]["headers"]["Authorization"] == "Bearer key2"
        
        await client.generate("sys", "user")
        assert mock_post.call_args_list[2][1]["headers"]["Authorization"] == "Bearer key1"


@pytest.mark.asyncio
async def test_openrouter_client_rate_limit_rotation() -> None:
    client = OpenRouterClient(api_keys=["key1", "key2"], model="deepseek/deepseek-chat")
    
    mock_response_429 = MagicMock()
    mock_response_429.status_code = 429
    
    mock_response_200 = MagicMock()
    mock_response_200.status_code = 200
    mock_response_200.json.return_value = {
        "choices": [{"message": {"content": "Success content"}}]
    }
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=[mock_response_429, mock_response_200]) as mock_post:
        result = await client.generate("sys", "user")
        assert result == "Success content"
        assert mock_post.call_count == 2
        assert mock_post.call_args_list[0][1]["headers"]["Authorization"] == "Bearer key1"
        assert mock_post.call_args_list[1][1]["headers"]["Authorization"] == "Bearer key2"


@pytest.mark.asyncio
async def test_openrouter_client_all_failed() -> None:
    client = OpenRouterClient(api_keys=["key1", "key2"])
    
    mock_response_429 = MagicMock()
    mock_response_429.status_code = 429
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response_429):
        with pytest.raises(RuntimeError) as exc_info:
            await client.generate("sys", "user")
        assert "All 2 OpenRouter API keys failed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_openrouter_client_structured_output() -> None:
    client = OpenRouterClient(api_keys=["key1"])
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": '{"name": "Bob", "age": 25}'}}]
    }
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        result = await client.structured_output("sys", "user", DummySchema)
        assert isinstance(result, DummySchema)
        assert result.name == "Bob"
        assert result.age == 25


def test_settings_from_env_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEXT2SQL_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEYS", "or-key-a, or-key-b")
    monkeypatch.setenv("OPENROUTER_MODEL", "meta-llama/llama-3-70b-instruct")
    
    settings = Settings.from_env()
    assert settings.llm_provider == "openrouter"
    assert settings.openrouter_api_keys == ["or-key-a", "or-key-b"]
    assert settings.openrouter_model == "meta-llama/llama-3-70b-instruct"
    
    client = get_llm_client(settings)
    assert isinstance(client, OpenRouterClient)
    assert client.api_keys == ["or-key-a", "or-key-b"]
    assert client.model == "meta-llama/llama-3-70b-instruct"


def test_settings_openrouter_individual_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEXT2SQL_LLM_PROVIDER", "openrouter")
    monkeypatch.delenv("OPENROUTER_API_KEYS", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key-single")
    
    settings = Settings.from_env()
    assert settings.openrouter_api_keys == ["or-key-single"]

    # Test numbered keys
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY_1", "or-key-num1")
    monkeypatch.setenv("OPENROUTER_API_KEY_2", "or-key-num2")
    settings = Settings.from_env()
    assert settings.openrouter_api_keys == ["or-key-num1", "or-key-num2"]
