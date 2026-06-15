import asyncio
import asyncpg
import sys

async def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
        
    db_url = "postgresql://app_user:app_password@localhost:54331/app_db"
    conn = await asyncpg.connect(db_url)
    
    # $1: user_id
    # $2: date_start
    # $3: date_end
    # $4: speaker_name
    from datetime import date
    
    user_id = '00000000-0000-0000-0000-000000000000'
    date_start = date_end = date(2026, 5, 9)
    speaker_name = '伊藤'
    
    q1 = '''
        SELECT DISTINCT ct2.speaker, 'PART 1' as part, ct2.text
        FROM chunks_turn ct2
        JOIN transcripts t2 ON ct2.transcript_id = t2.id
        WHERE ct2.speaker = $4::text
          AND ($1::uuid IS NULL OR t2.user_id = $1::uuid)
          AND ($2::date IS NULL OR t2.meeting_date >= $2::date)
          AND ($3::date IS NULL OR t2.meeting_date <= $3::date)
    '''
    q2 = '''
        SELECT DISTINCT ct2.speaker, 'PART 2' as part, ct2.text
        FROM chunks_turn ct2
        JOIN transcripts t2 ON ct2.transcript_id = t2.id
        WHERE ct2.text ILIKE '%' || $4::text || '%'
          AND ($1::uuid IS NULL OR t2.user_id = $1::uuid)
          AND ($2::date IS NULL OR t2.meeting_date >= $2::date)
          AND ($3::date IS NULL OR t2.meeting_date <= $3::date)
    '''
    
    rows1 = await conn.fetch(q1, user_id, date_start, date_end, speaker_name)
    rows2 = await conn.fetch(q2, user_id, date_start, date_end, speaker_name)
    
    print("Part 1 results:")
    for r in rows1:
        print(f"  {r['speaker']}: {r['text']}")
        
    print("Part 2 results:")
    for r in rows2:
        print(f"  {r['speaker']}: {r['text']}")
        
    # Let's run full UNION with LIMIT 1
    full_q = f'''
        WITH speaker_resolved AS (
          (
            SELECT ct2.speaker
            FROM chunks_turn ct2
            JOIN transcripts t2 ON ct2.transcript_id = t2.id
            WHERE ct2.speaker = $4::text
              AND ($1::uuid IS NULL OR t2.user_id = $1::uuid)
              AND ($2::date IS NULL OR t2.meeting_date >= $2::date)
              AND ($3::date IS NULL OR t2.meeting_date <= $3::date)
            LIMIT 1
          )
          UNION ALL
          (
            SELECT ct2.speaker
            FROM chunks_turn ct2
            JOIN transcripts t2 ON ct2.transcript_id = t2.id
            WHERE ct2.text ILIKE '%' || $4::text || '%'
              AND ($1::uuid IS NULL OR t2.user_id = $1::uuid)
              AND ($2::date IS NULL OR t2.meeting_date >= $2::date)
              AND ($3::date IS NULL OR t2.meeting_date <= $3::date)
            ORDER BY ct2.time_start_sec ASC
            LIMIT 1
          )
          LIMIT 1
        )
        SELECT speaker FROM speaker_resolved
    '''
    resolved = await conn.fetch(full_q, user_id, date_start, date_end, speaker_name)
    print("Full resolved speaker:")
    for r in resolved:
        print(f"  {r['speaker']}")
        
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())
