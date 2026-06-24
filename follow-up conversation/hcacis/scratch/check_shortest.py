import asyncio, asyncpg
async def test():
    pool = await asyncpg.create_pool('postgresql://app_user:app_password@localhost:54331/app_db')
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id, duration_seconds FROM transcripts WHERE meeting_date BETWEEN '2026-05-01' AND '2026-05-31' ORDER BY duration_seconds ASC LIMIT 1")
        print(dict(row) if row else 'None')
    await pool.close()
asyncio.run(test())
