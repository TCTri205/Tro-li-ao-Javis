import asyncio
import asyncpg
import os
import json
import sys
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("NUMERIC_SQL_DATABASE_URL", "postgresql://app_user:app_password@localhost:54331/app_db")

async def main():
    sys.stdout.reconfigure(encoding='utf-8')
    conn = await asyncpg.connect(DB_URL)
    print("--- ACTIVE CACHES ---")
    caches = await conn.fetch("SELECT * FROM session_context_cache WHERE session_id = 'session_neg'")
    for c in caches:
        c_dict = dict(c)
        print(f"Topic: {c_dict['topic_key']}, Pipeline: {c_dict['last_pipeline']}")
        payload_row = await conn.fetchrow("SELECT * FROM session_context_payload WHERE cache_id = $1", c_dict['id'])
        if payload_row:
            p_dict = dict(payload_row)
            # Safe print using json.dumps with ensure_ascii=False
            summary_str = json.dumps(json.loads(p_dict['summary_context']) if p_dict['summary_context'] else None, ensure_ascii=False)
            print(f"  Summary Context: {summary_str}")
            
    print("\n--- ENTITY INDEX ---")
    entities = await conn.fetch("SELECT * FROM session_entity_index WHERE session_id = 'session_neg'")
    for e in entities:
        e_dict = dict(e)
        display_names_str = json.dumps(e_dict['display_names'], ensure_ascii=False)
        print(f"Entity: {e_dict['entity_id']}, Type: {e_dict['entity_type']}, Display Names: {display_names_str}, Cache Slot: {e_dict['cache_slot_id']}")
        
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
