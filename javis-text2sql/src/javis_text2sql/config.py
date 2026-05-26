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


@dataclass(frozen=True)
class Settings:
    database_url: str | None = None
    readonly_database_url: str | None = None
    statement_timeout_ms: int = 5000

    @classmethod
    def from_env(cls) -> "Settings":
        timeout_raw = os.getenv("TEXT2SQL_STATEMENT_TIMEOUT_MS", "5000")
        return cls(
            database_url=os.getenv("TEXT2SQL_DATABASE_URL"),
            readonly_database_url=os.getenv("TEXT2SQL_READONLY_DATABASE_URL"),
            statement_timeout_ms=int(timeout_raw),
        )


def require_database_url(value: str | None, env_name: str = "TEXT2SQL_DATABASE_URL") -> str:
    if not value:
        raise RuntimeError(f"{env_name} is required for this command")
    return value
