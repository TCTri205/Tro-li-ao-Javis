import asyncio, asyncpg
async def test():
    pool = await asyncpg.create_pool('postgresql://app_user:app_password@localhost:54331/app_db')
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT meeting_date FROM transcripts ORDER BY meeting_date ASC")
        print("Dates in DB:")
        for r in rows:
            print(r['meeting_date'])
    await pool.close()
asyncio.run(test())
