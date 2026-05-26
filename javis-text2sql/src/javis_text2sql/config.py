from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()



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
                
        return cls(
            database_url=os.getenv("TEXT2SQL_DATABASE_URL"),
            readonly_database_url=os.getenv("TEXT2SQL_READONLY_DATABASE_URL"),
            statement_timeout_ms=int(timeout_raw),
            llm_provider=provider,
            groq_api_keys=keys,
            groq_model=model,
            redis_url=os.getenv("TEXT2SQL_REDIS_URL", "redis://localhost:6379/0"),
        )


def require_database_url(value: str | None, env_name: str = "TEXT2SQL_DATABASE_URL") -> str:
    if not value:
        raise RuntimeError(f"{env_name} is required for this command")
    return value
