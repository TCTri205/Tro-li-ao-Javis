import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("NUMERIC_SQL_DATABASE_URL")

async def main():
    conn = await asyncpg.connect(DB_URL)
    count = await conn.fetchval("SELECT count(*) FROM transcripts")
    print(f"Transcripts: {count}")
    count = await conn.fetchval("SELECT count(*) FROM chunks_turn")
    print(f"Chunks Turn: {count}")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
