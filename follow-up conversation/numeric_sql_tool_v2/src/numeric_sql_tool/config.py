from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv(override=True)


@dataclass(frozen=True)
class Settings:
    database_url: str | None = None
    llm_provider: str = "groq"
    groq_api_keys: list[str] = field(default_factory=list)
    groq_model: str = "llama-3.3-70b-versatile"
    statement_timeout_ms: int = 5000

    @classmethod
    def from_env(cls) -> "Settings":
        timeout_raw = os.getenv("NUMERIC_SQL_STATEMENT_TIMEOUT_MS", "5000")
        provider = os.getenv("NUMERIC_SQL_LLM_PROVIDER", "groq")
        model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

        keys: list[str] = []
        raw_keys = os.getenv("GROQ_API_KEYS")
        if raw_keys:
            keys.extend([k.strip() for k in raw_keys.split(",") if k.strip()])
        else:
            single_key = os.getenv("GROQ_API_KEY")
            if single_key:
                keys.append(single_key.strip())
            i = 1
            while i <= 20:
                key_i = os.getenv(f"GROQ_API_KEY_{i}")
                if key_i:
                    keys.append(key_i.strip())
                i += 1

        return cls(
            database_url=os.getenv("NUMERIC_SQL_DATABASE_URL"),
            llm_provider=provider,
            groq_api_keys=keys,
            groq_model=model,
            statement_timeout_ms=int(timeout_raw),
        )


def require_database_url(value: str | None, env_name: str = "NUMERIC_SQL_DATABASE_URL") -> str:
    if not value:
        raise RuntimeError(f"{env_name} is required")
    return value
