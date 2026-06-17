import asyncio
import asyncpg
import os
import re
import sys
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("NUMERIC_SQL_DATABASE_URL", "postgresql://app_user:app_password@localhost:54331/app_db")

def match_pronoun(query: str, display_names: list) -> bool:
    query_lower = query.lower()
    for name in display_names:
        name_lower = name.lower()
        if len(name_lower) <= 2:
            is_ascii_alnum = name_lower.isalnum() and name_lower.isascii()
            pattern = rf"\b{re.escape(name_lower)}\b" if is_ascii_alnum else re.escape(name_lower)
            if re.search(pattern, query_lower):
                return True
        else:
            if name_lower in query_lower:
                return True
    return False

async def main():
    sys.stdout.reconfigure(encoding='utf-8')
    conn = await asyncpg.connect(DB_URL)
    
    entities = await conn.fetch("""
        SELECT e.cache_slot_id, e.entity_id, e.entity_type, e.display_names, c.topic_key, c.last_pipeline, p.summary_context
        FROM session_entity_index e
        JOIN session_context_cache c ON e.cache_slot_id = c.id
        LEFT JOIN session_context_payload p ON c.id = p.cache_id
        WHERE e.session_id = 'session_neg'
    """)
    
    query = "GT_06の通話の詳細"
    matched_slots = []
    print("--- ALL ENTITIES FOR session_neg ---")
    for ent in entities:
        is_match = match_pronoun(query, ent['display_names'])
        print(f"Entity: {ent['entity_id']}, topic_key: {ent['topic_key']}, is_match: {is_match}")
        if is_match:
            matched_slots.append(ent)
            
    # Deduplicate matched slots by cache_slot_id
    unique_matches = {}
    for m in matched_slots:
        unique_matches[m['cache_slot_id']] = m
        
    print(f"\nUnique Matches Count: {len(unique_matches)}")
    for cache_slot_id, matched_ent in unique_matches.items():
        print(f"Cache Slot ID: {cache_slot_id}, topic_key: {matched_ent['topic_key']}")
        
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
