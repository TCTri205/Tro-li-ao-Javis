from __future__ import annotations

import os

import pytest

from javis_text2sql.db.admin import apply_migrations, create_pool, seed_entity_aliases, verify_views, seed_golden_queries
from javis_text2sql.etl.samples import ingest_sample_files
from javis_text2sql.llm.fixture import FixtureLLMClient


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_migrate_seed_ingest_and_verify_views() -> None:
    database_url = os.getenv("TEXT2SQL_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEXT2SQL_TEST_DATABASE_URL is not set")

    pool = await create_pool(database_url)
    try:
        async with pool.acquire() as conn:
            await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO public;")
    finally:
        await pool.close()

    await apply_migrations(database_url)
    await seed_entity_aliases(database_url)
    await seed_golden_queries(database_url)
    pool = await create_pool(database_url)
    try:
        async with pool.acquire() as conn:
            for table in ["commitments", "turns", "passages", "meetings", "entity_aliases", "golden_queries"]:
                await conn.execute(f"TRUNCATE {table} RESTART IDENTITY CASCADE")
        await seed_entity_aliases(database_url)
        await seed_golden_queries(database_url)
        await ingest_sample_files(pool, FixtureLLMClient())
    finally:
        await pool.close()

    report = await verify_views(database_url)
    assert report["counts"]["meetings"] == 3
    assert report["counts"]["v_amounts"] >= 1
    assert report["counts"]["v_commitments"] >= 7
    assert report["counts"]["v_speaker_turns"] > 0
    assert report["integrity"]["orphan_passages"] == 0
