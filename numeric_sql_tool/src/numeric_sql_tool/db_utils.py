from __future__ import annotations

from pathlib import Path
from typing import Any


async def create_pool(database_url: str, **kwargs: Any) -> Any:
    import asyncpg

    return await asyncpg.create_pool(database_url, **kwargs)


def _read_sql(path: Path) -> str:
    return path.read_text(encoding="utf-8")


async def apply_sql_file(conn: Any, path: Path) -> None:
    sql = _read_sql(path)
    if not sql.strip():
        return
    await conn.execute(sql)


# Parent tables must load before child tables (FK order).
_DEFAULT_SQL_LOAD_ORDER = (
    "transcripts.sql",
    "chunks_passage.sql",
    "chunks_turn.sql",
    "company_documents.sql",
    "company_chunks.sql",
)


def _sql_file_sort_key(path: Path) -> tuple[int, str]:
    name = path.name
    try:
        return (_DEFAULT_SQL_LOAD_ORDER.index(name), name)
    except ValueError:
        return (len(_DEFAULT_SQL_LOAD_ORDER), name)


async def apply_sql_dir(conn: Any, folder: Path) -> list[str]:
    applied: list[str] = []
    for path in sorted(folder.glob("*.sql"), key=_sql_file_sort_key):
        await apply_sql_file(conn, path)
        applied.append(path.name)
    return applied
