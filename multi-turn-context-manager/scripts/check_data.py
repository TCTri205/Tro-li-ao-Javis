import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("NUMERIC_SQL_DATABASE_URL")

async def main():
    conn = await asyncpg.connect(DB_URL)
    rows = await conn.fetch("SELECT * FROM transcripts LIMIT 1")
    for r in rows:
        print(dict(r))
    
    rows = await conn.fetch("SELECT COUNT(*) FROM transcripts")
    print(f"transcripts count: {rows[0][0]}")
    
    rows = await conn.fetch("SELECT COUNT(*) FROM chunks_turn")
    print(f"chunks_turn count: {rows[0][0]}")
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
