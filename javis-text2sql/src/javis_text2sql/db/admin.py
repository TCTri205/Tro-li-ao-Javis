from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from javis_text2sql.config import MIGRATIONS_DIR, SEEDS_DIR


async def create_pool(database_url: str, **kwargs: Any) -> Any:
    import asyncpg

    return await asyncpg.create_pool(database_url, **kwargs)


async def apply_migrations(database_url: str, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    pool = await create_pool(database_url)
    applied: list[str] = []
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                for path in sorted(migrations_dir.glob("*.sql")):
                    await conn.execute(path.read_text(encoding="utf-8"))
                    applied.append(path.name)
    finally:
        await pool.close()
    return applied


async def seed_entity_aliases(database_url: str, seed_file: Path = SEEDS_DIR / "entity_aliases.csv") -> int:
    pool = await create_pool(database_url)
    rows = list(csv.DictReader(seed_file.read_text(encoding="utf-8-sig").splitlines()))
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.executemany(
                    """
                    INSERT INTO entity_aliases (canonical_name, alias, language, entity_type)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (alias, language)
                    DO UPDATE SET
                        canonical_name = EXCLUDED.canonical_name,
                        entity_type = EXCLUDED.entity_type
                    """,
                    [
                        (
                            row["canonical_name"],
                            row["alias"],
                            row["language"],
                            row.get("entity_type") or None,
                        )
                        for row in rows
                    ],
                )
    finally:
        await pool.close()
    return len(rows)


async def seed_golden_queries(
    database_url: str,
    embedding_client: Any = None,
) -> int:
    from javis_text2sql.llm.embeddings import get_embedding_client

    pool = await create_pool(database_url)
    embed_client = embedding_client or get_embedding_client()

    csv_file = Path("testcase-text2sql.csv")
    if not csv_file.exists():
        from javis_text2sql.config import PROJECT_ROOT
        csv_file = PROJECT_ROOT / "testcase-text2sql.csv"

    dataset = []
    if csv_file.exists():
        with open(csv_file, mode="r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)  # Skip header
            for row in reader:
                if len(row) >= 2:
                    q = row[0].strip()
                    sql_val = row[1].strip()
                    if q and sql_val:
                        dataset.append((q, sql_val))

    if not dataset:
        from javis_text2sql.query.prompt import FEW_SHOT_EXAMPLES
        dataset = FEW_SHOT_EXAMPLES

    questions = [q for q, _ in dataset]
    embeddings = await embed_client.embed_texts(questions)

    rows = []
    for (q, sql), emb in zip(dataset, embeddings):
        rows.append((q, sql, str(emb)))

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.executemany(
                    """
                    INSERT INTO golden_queries (question, sql, embedding)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (question)
                    DO UPDATE SET
                        sql = EXCLUDED.sql,
                        embedding = EXCLUDED.embedding
                    """,
                    rows,
                )
    finally:
        await pool.close()
    return len(rows)


async def verify_views(database_url: str) -> dict[str, Any]:
    pool = await create_pool(database_url)
    try:
        async with pool.acquire() as conn:
            counts: dict[str, int] = {}
            for table in ["meetings", "passages", "turns", "commitments", "entity_aliases"]:
                counts[table] = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
            for view in [
                "v_topics",
                "v_commitments",
                "v_amounts",
                "v_action_items",
                "v_open_questions",
                "v_statements",
                "v_dates",
                "v_speaker_turns",
            ]:
                counts[view] = await conn.fetchval(f"SELECT COUNT(*) FROM {view}")

            integrity = {
                "orphan_passages": await conn.fetchval(
                    "SELECT COUNT(*) FROM passages p LEFT JOIN meetings m ON m.id = p.meeting_id WHERE m.id IS NULL"
                ),
                "orphan_turns": await conn.fetchval(
                    "SELECT COUNT(*) FROM turns t LEFT JOIN passages p ON p.id = t.passage_id WHERE p.id IS NULL"
                ),
                "orphan_commitments": await conn.fetchval(
                    "SELECT COUNT(*) FROM commitments c LEFT JOIN passages p ON p.id = c.passage_id WHERE p.id IS NULL"
                ),
                "llm_failed_passages": await conn.fetchval(
                    "SELECT COUNT(*) FROM passages WHERE enrichment_status = 'llm_failed'"
                ),
            }
            samples = {
                "commitments": [dict(row) for row in await conn.fetch("SELECT * FROM v_commitments LIMIT 20")],
                "amounts": [dict(row) for row in await conn.fetch("SELECT * FROM v_amounts LIMIT 20")],
                "speaker_turns": [dict(row) for row in await conn.fetch("SELECT * FROM v_speaker_turns LIMIT 20")],
            }
            return {"counts": counts, "integrity": integrity, "samples": samples}
    finally:
        await pool.close()
