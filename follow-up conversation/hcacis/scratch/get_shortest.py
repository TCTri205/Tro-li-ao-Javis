import asyncio, asyncpg
async def test():
    pool = await asyncpg.create_pool('postgresql://app_user:app_password@localhost:54331/app_db')
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT raw_text, summary FROM transcripts WHERE id = '9154186b-e939-43d7-b736-fd7b42f5a57c'")
        if row:
            print("RAW TEXT:")
            print(row['raw_text'])
            print("SUMMARY:")
            print(row['summary'])
    await pool.close()
asyncio.run(test())
