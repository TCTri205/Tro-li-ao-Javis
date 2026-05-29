from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

# Import Settings early to run load_dotenv before monkeypatching in tests
from javis_text2sql.config import Settings
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


@pytest.mark.asyncio
async def test_groq_client_fallback_to_gemini() -> None:
    from javis_text2sql.llm.gemini import GeminiClient
    gemini_client = GeminiClient(api_keys=["gemini_key"], model="gemini-2.5-flash")
    groq_client = GroqClient(api_keys=["groq_key1"], gemini_client=gemini_client)

    mock_response_groq = MagicMock()
    mock_response_groq.status_code = 429

    mock_response_gemini = MagicMock()
    mock_response_gemini.status_code = 200
    mock_response_gemini.json.return_value = {
        "choices": [{"message": {"content": "Gemini success content"}}]
    }

    # Since num_keys = 1, it will try Groq 3 times (max_attempts = 1 * 3 = 3) before falling back.
    # We patch asyncio.sleep to prevent the test from actually sleeping.
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=[mock_response_groq, mock_response_groq, mock_response_groq, mock_response_gemini]) as mock_post:
        
        result = await groq_client.generate("sys", "user")
        assert result == "Gemini success content"
        assert mock_post.call_count == 4
        assert mock_sleep.call_count > 0
        
        # Verify Groq was called first 3 times
        for i in range(3):
            assert mock_post.call_args_list[i][0][0] == "https://api.groq.com/openai/v1/chat/completions"
            assert mock_post.call_args_list[i][1]["headers"]["Authorization"] == "Bearer groq_key1"
        
        # Verify Gemini was called 4th
        assert mock_post.call_args_list[3][0][0] == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        assert mock_post.call_args_list[3][1]["headers"]["Authorization"] == "Bearer gemini_key"
        assert mock_post.call_args_list[3][1]["json"]["model"] == "gemini-2.5-flash"


@pytest.mark.asyncio
async def test_gemini_client_success() -> None:
    from javis_text2sql.llm.gemini import GeminiClient
    client = GeminiClient(api_keys=["gemini_key"], model="gemini-2.5-flash")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Hello Gemini"}}]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
        result = await client.generate("system_prompt", "user_prompt")
        assert result == "Hello Gemini"
        assert mock_post.call_count == 1
        assert mock_post.call_args[0][0] == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        headers = mock_post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer gemini_key"


@pytest.mark.asyncio
async def test_gemini_client_round_robin() -> None:
    from javis_text2sql.llm.gemini import GeminiClient
    client = GeminiClient(api_keys=["gemini-key1", "gemini-key2"], model="gemini-2.5-flash")
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Hello"}}]
    }
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
        await client.generate("sys", "user")
        assert mock_post.call_args_list[0][1]["headers"]["Authorization"] == "Bearer gemini-key1"
        
        await client.generate("sys", "user")
        assert mock_post.call_args_list[1][1]["headers"]["Authorization"] == "Bearer gemini-key2"
        
        await client.generate("sys", "user")
        assert mock_post.call_args_list[2][1]["headers"]["Authorization"] == "Bearer gemini-key1"


def test_settings_gemini_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEXT2SQL_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEYS", "my-gemini-key1, my-gemini-key2")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-pro")
    
    from javis_text2sql.config import Settings
    from javis_text2sql.llm import get_llm_client
    from javis_text2sql.llm.gemini import GeminiClient
    
    settings = Settings.from_env()
    assert settings.llm_provider == "gemini"
    assert settings.gemini_api_keys == ["my-gemini-key1", "my-gemini-key2"]
    assert settings.gemini_model == "gemini-2.5-pro"
    
    client = get_llm_client(settings)
    assert isinstance(client, GeminiClient)
    assert client.api_keys == ["my-gemini-key1", "my-gemini-key2"]
    assert client.model == "gemini-2.5-pro"


def test_settings_groq_with_gemini_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEXT2SQL_LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEYS", "groq-key")
    monkeypatch.setenv("GEMINI_API_KEYS", "fallback-gemini-key1,fallback-gemini-key2")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    
    from javis_text2sql.config import Settings
    from javis_text2sql.llm import get_llm_client
    
    settings = Settings.from_env()
    client = get_llm_client(settings)
    assert isinstance(client, GroqClient)
    assert client.gemini_client is not None
    assert client.gemini_client.api_keys == ["fallback-gemini-key1", "fallback-gemini-key2"]
    assert client.gemini_client.model == "gemini-2.5-flash"

