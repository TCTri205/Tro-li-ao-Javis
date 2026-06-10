import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
import sys

# Load env variables from .env file
ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

sys.path.insert(0, str(ROOT / "src"))
from numeric_sql_tool.db_utils import create_pool, apply_sql_file, apply_sql_dir

async def main():
    db_url = os.getenv("NUMERIC_SQL_DATABASE_URL")
    if not db_url:
        print("Error: NUMERIC_SQL_DATABASE_URL is not set in .env")
        return
        
    print(f"Connecting to database at {db_url}...")
    pool = await create_pool(db_url)
    
    try:
        async with pool.acquire() as conn:
            # 1. Truncate existing meeting tables
            print("Truncating meeting tables (transcripts, chunks_passage, chunks_turn)...")
            await conn.execute("TRUNCATE TABLE public.chunks_turn, public.chunks_passage, public.transcripts CASCADE;")
            
            # 2. Load new SQL data
            print("Loading new SQL data from db/data...")
            applied = await apply_sql_dir(conn, ROOT / "db" / "data")
            print(f"Successfully loaded data files: {applied}")
            
            # Verification Query
            print("\nVerifying transcripts in DB:")
            rows = await conn.fetch("SELECT session_id, meeting_date, duration_seconds, speaker_count FROM public.transcripts ORDER BY session_id;")
            for r in rows:
                print(f"  Session: {r['session_id']}, Date: {r['meeting_date']}, Duration: {r['duration_seconds']}s, Speakers: {r['speaker_count']}")
            
    except Exception as e:
        print(f"Error resetting database: {e}")
    finally:
        await pool.close()

if __name__ == "__main__":
    asyncio.run(main())
