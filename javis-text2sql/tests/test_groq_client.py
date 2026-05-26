from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from javis_text2sql.llm.groq import GroqClient


class DummySchema(BaseModel):
    name: str
    age: int


@pytest.mark.asyncio
async def test_groq_client_success() -> None:
    client = GroqClient(api_keys=["key1", "key2"], model="llama-3.3-70b-versatile")
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Hello world"
                }
            }
        ]
    }
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
        result = await client.generate("system_prompt", "user_prompt")
        assert result == "Hello world"
        assert mock_post.call_count == 1
        headers = mock_post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer key1"


@pytest.mark.asyncio
async def test_groq_client_round_robin() -> None:
    client = GroqClient(api_keys=["key1", "key2"], model="llama-3.3-70b-versatile")
    
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
async def test_groq_client_rate_limit_rotation() -> None:
    client = GroqClient(api_keys=["key1", "key2"], model="llama-3.3-70b-versatile")
    
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
async def test_groq_client_all_failed() -> None:
    client = GroqClient(api_keys=["key1", "key2"])
    
    mock_response_429 = MagicMock()
    mock_response_429.status_code = 429
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response_429):
        with pytest.raises(RuntimeError) as exc_info:
            await client.generate("sys", "user")
        assert "All 2 Groq API keys failed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_groq_client_structured_output() -> None:
    client = GroqClient(api_keys=["key1"])
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": '{"name": "Alice", "age": 30}'}}]
    }
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        result = await client.structured_output("sys", "user", DummySchema)
        assert isinstance(result, DummySchema)
        assert result.name == "Alice"
        assert result.age == 30


def test_settings_from_env_rotation_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEXT2SQL_LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEYS", "key-a, key-b ,key-c")
    monkeypatch.setenv("GROQ_MODEL", "my-custom-model")
    
    from javis_text2sql.config import Settings
    from javis_text2sql.llm import get_llm_client
    
    settings = Settings.from_env()
    assert settings.llm_provider == "groq"
    assert settings.groq_api_keys == ["key-a", "key-b", "key-c"]
    assert settings.groq_model == "my-custom-model"
    
    client = get_llm_client(settings)
    assert isinstance(client, GroqClient)
    assert client.api_keys == ["key-a", "key-b", "key-c"]
    assert client.model == "my-custom-model"


def test_settings_individual_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEXT2SQL_LLM_PROVIDER", "groq")
    monkeypatch.delenv("GROQ_API_KEYS", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "key-single")
    
    from javis_text2sql.config import Settings
    settings = Settings.from_env()
    assert settings.groq_api_keys == ["key-single"]

    # Test numbered keys
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY_1", "key-num1")
    monkeypatch.setenv("GROQ_API_KEY_2", "key-num2")
    settings = Settings.from_env()
    assert settings.groq_api_keys == ["key-num1", "key-num2"]

