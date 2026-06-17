import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("NUMERIC_SQL_DATABASE_URL")

async def main():
    conn = await asyncpg.connect(DB_URL)
    rows = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    for r in rows:
        print(f" - {r['table_name']}")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
