import asyncio
import asyncpg
import os
import json
import re
import sys
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("NUMERIC_SQL_DATABASE_URL", "postgresql://app_user:app_password@localhost:54331/app_db")

def is_date_mismatch(query: str, summary_context) -> bool:
    if not summary_context:
        return False
    if isinstance(summary_context, str):
        try:
            summary_context = json.loads(summary_context)
        except Exception:
            return False
    if not isinstance(summary_context, dict):
        return False
    key_attrs = summary_context.get("key_attributes") or {}
    slot_date_str = key_attrs.get("date") # e.g. "2026-05-04"
    if not slot_date_str:
        return False
        
    try:
        dt = datetime.strptime(slot_date_str, "%Y-%m-%d")
        day, month, year = dt.day, dt.month, dt.year
    except Exception:
        try:
            dt = datetime.strptime(slot_date_str, "%d/%m/%Y")
            day, month, year = dt.day, dt.month, dt.year
        except Exception:
            return False
        
    # Extract D/M or D/M/Y or D-M from query
    query_dates = re.findall(r'\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b', query)
    # Also support Japanese date format: X月Y日 or YYYY年X月Y日
    ja_dates = re.findall(r'(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日', query)
    
    # Check query_dates
    for q_day_str, q_month_str, q_year_str in query_dates:
        q_day = int(q_day_str)
        q_month = int(q_month_str)
        if q_day == day and q_month == month:
            if q_year_str:
                q_year = int(q_year_str)
                if q_year < 100:
                    q_year += 2000
                if q_year == year:
                    return False
            else:
                return False
                
    # Check ja_dates
    for q_year_str, q_month_str, q_day_str in ja_dates:
        q_day = int(q_day_str)
        q_month = int(q_month_str)
        if q_day == day and q_month == month:
            if q_year_str:
                q_year = int(q_year_str)
                if q_year == year:
                    return False
            else:
                return False
                
    if not query_dates and not ja_dates:
        return False
        
    return True # Mismatch

def is_gt_mismatch(query: str, topic_key: str, summary_context=None) -> bool:
    if not topic_key:
        return False
    query_gts = re.findall(r'GT_\d+', query, re.IGNORECASE)
    if not query_gts:
        return False

    context_dict = {}
    if summary_context:
        if isinstance(summary_context, str):
            try:
                context_dict = json.loads(summary_context)
            except Exception:
                pass
        elif isinstance(summary_context, dict):
            context_dict = summary_context

    gt_sessions = []
    if isinstance(context_dict, dict):
        key_attrs = context_dict.get("key_attributes") or {}
        gt_sessions = key_attrs.get("gt_sessions") or []
        entity_id = context_dict.get("entity_id")
        if entity_id and entity_id not in gt_sessions:
            gt_sessions.append(entity_id)

    gt_sessions_upper = [s.upper() for s in gt_sessions if isinstance(s, str)]

    for gt in query_gts:
        gt_upper = gt.upper()
        if gt_upper in topic_key.upper():
            return False
        if gt_upper in gt_sessions_upper:
            return False
    return True

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
    
    for e in entities:
        if e['entity_id'] == 'GT_06':
            gt_mismatch = is_gt_mismatch("GT_06の通話の詳細", e['topic_key'], e['summary_context'])
            date_mismatch = is_date_mismatch("GT_06の通話の詳細", e['summary_context'])
            print(f"Matched Entity: {e['entity_id']}, topic_key: {e['topic_key']}")
            print(f"  is_gt_mismatch: {gt_mismatch}")
            print(f"  is_date_mismatch: {date_mismatch}")
            print(f"  Combined OR: {gt_mismatch or date_mismatch}")
            
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
