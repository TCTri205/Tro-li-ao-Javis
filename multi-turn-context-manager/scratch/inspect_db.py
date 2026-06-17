import asyncio
import asyncpg
import os
import sys
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()
DB_URL = os.getenv("NUMERIC_SQL_DATABASE_URL", "postgresql://app_user:app_password@localhost:54331/app_db")

async def main():
    conn = await asyncpg.connect(DB_URL)
    print("--- session_context_cache ---")
    rows = await conn.fetch("SELECT id, session_id, topic_key, last_pipeline FROM session_context_cache WHERE session_id = 'v2_entity_session'")
    for r in rows:
        print(dict(r))
        
    print("\n--- session_entity_index ---")
    rows = await conn.fetch("SELECT id, session_id, cache_slot_id, entity_id, entity_type, display_names FROM session_entity_index WHERE session_id = 'v2_entity_session'")
    for r in rows:
        print(dict(r))
        
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
