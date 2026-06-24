import asyncio, asyncpg
async def test():
    pool = await asyncpg.create_pool('postgresql://app_user:app_password@localhost:54331/app_db')
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT meeting_date, summary, speaker_count FROM transcripts WHERE meeting_date = '2026-06-08'")
        for row in rows:
            print(dict(row))
    await pool.close()
asyncio.run(test())
