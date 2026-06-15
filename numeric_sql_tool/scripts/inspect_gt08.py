import asyncio
import asyncpg
import sys

async def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    conn = await asyncpg.connect('postgresql://app_user:app_password@localhost:54331/app_db')
    rows = await conn.fetch('''
        SELECT t.session_id, ct.speaker, ct.text 
        FROM chunks_turn ct 
        JOIN transcripts t ON ct.transcript_id = t.id 
        WHERE t.session_id IN ('GT_08', 'GT_09', 'GT_06')
        ORDER BY t.session_id, ct.time_start_sec
    ''')
    for r in rows:
        print(f"[{r['session_id']}] {r['speaker']}: {r['text']}")
    await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
