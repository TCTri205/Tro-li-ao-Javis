from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file if it exists, overriding existing env vars
load_dotenv(override=True)



PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"
SEEDS_DIR = PROJECT_ROOT / "seeds"
SAMPLE_DATA_DIR = PROJECT_ROOT / "tests" / "fixtures" / "sample_data"


from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    database_url: str | None = None
    readonly_database_url: str | None = None
    statement_timeout_ms: int = 5000
    llm_provider: str = "groq"
    groq_api_keys: list[str] = field(default_factory=list)
    groq_model: str = "llama-3.3-70b-versatile"
    gemini_api_keys: list[str] = field(default_factory=list)
    gemini_model: str = "gemini-2.5-flash"
    openrouter_api_keys: list[str] = field(default_factory=list)
    openrouter_model: str = "deepseek/deepseek-chat"
    redis_url: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        timeout_raw = os.getenv("TEXT2SQL_STATEMENT_TIMEOUT_MS", "5000")
        
        provider = os.getenv("TEXT2SQL_LLM_PROVIDER", "groq")
        model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        
        keys = []
        raw_keys = os.getenv("GROQ_API_KEYS")
        if raw_keys:
            keys.extend([k.strip() for k in raw_keys.split(",") if k.strip()])
        else:
            single_key = os.getenv("GROQ_API_KEY")
            if single_key:
                keys.append(single_key.strip())
            
            # Also check for individual keys like GROQ_API_KEY_1, GROQ_API_KEY_2
            i = 1
            while i <= 20:  # check up to 20 keys
                key_i = os.getenv(f"GROQ_API_KEY_{i}")
                if key_i:
                    keys.append(key_i.strip())
                i += 1

        gemini_keys = []
        raw_gemini_keys = os.getenv("GEMINI_API_KEYS")
        if raw_gemini_keys:
            gemini_keys.extend([k.strip() for k in raw_gemini_keys.split(",") if k.strip()])
        else:
            single_gemini_key = os.getenv("GEMINI_API_KEY")
            if single_gemini_key:
                gemini_keys.append(single_gemini_key.strip())
            
            # Also check for individual keys like GEMINI_API_KEY_1, GEMINI_API_KEY_2
            i = 1
            while i <= 20:  # check up to 20 keys
                key_i = os.getenv(f"GEMINI_API_KEY_{i}")
                if key_i:
                    gemini_keys.append(key_i.strip())
                i += 1

        gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

        openrouter_keys = []
        raw_openrouter_keys = os.getenv("OPENROUTER_API_KEYS")
        if raw_openrouter_keys:
            openrouter_keys.extend([k.strip() for k in raw_openrouter_keys.split(",") if k.strip()])
        else:
            single_openrouter_key = os.getenv("OPENROUTER_API_KEY")
            if single_openrouter_key:
                openrouter_keys.append(single_openrouter_key.strip())
            
            # Also check for individual keys like OPENROUTER_API_KEY_1, OPENROUTER_API_KEY_2
            i = 1
            while i <= 20:  # check up to 20 keys
                key_i = os.getenv(f"OPENROUTER_API_KEY_{i}")
                if key_i:
                    openrouter_keys.append(key_i.strip())
                i += 1

        openrouter_model = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat")
                
        return cls(
            database_url=os.getenv("TEXT2SQL_DATABASE_URL"),
            readonly_database_url=os.getenv("TEXT2SQL_READONLY_DATABASE_URL"),
            statement_timeout_ms=int(timeout_raw),
            llm_provider=provider,
            groq_api_keys=keys,
            groq_model=model,
            gemini_api_keys=gemini_keys,
            gemini_model=gemini_model,
            openrouter_api_keys=openrouter_keys,
            openrouter_model=openrouter_model,
            redis_url=os.getenv("TEXT2SQL_REDIS_URL", "redis://localhost:6379/0"),
        )


def require_database_url(value: str | None, env_name: str = "TEXT2SQL_DATABASE_URL") -> str:
    if not value:
        raise RuntimeError(f"{env_name} is required for this command")
    return value
