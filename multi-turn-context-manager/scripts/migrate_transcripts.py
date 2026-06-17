import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("NUMERIC_SQL_DATABASE_URL", "postgresql://app_user:app_password@localhost:54331/app_db")

async def main():
    print(f"Connecting to database at {DB_URL}...")
    conn = await asyncpg.connect(DB_URL)
    
    try:
        # Standardize session_ids
        migrations = [
            ("GT_01", "ingest-media-gt_01-2026-05-01"),
            ("GT_02", "ingest-media-gt_02-2026-05-02"),
            ("GT_03", "ingest-media-gt_03-2026-05-03"),
            ("GT_04", "ingest-media-gt_04-2026-05-04"),
            ("GT_05", "ingest-media-gt_05-2026-05-05"),
            ("GT_06", "ingest-media-gt_06-2026-05-06"),
            ("GT_07", "ingest-media-gt_07-2026-05-07"),
            ("GT_08", "ingest-media-gt_08-2026-05-08"),
            ("GT_09", "ingest-media-gt_09-2026-05-09"),
        ]
        
        print("Running transcript migration...")
        async with conn.transaction():
            for canonical, original in migrations:
                rows_updated = await conn.execute(
                    "UPDATE transcripts SET session_id = $1 WHERE session_id = $2",
                    canonical, original
                )
                print(f"Updated {original} -> {canonical}: {rows_updated}")
                
        print("Transcript migration completed successfully!")
        
        # Verify the updated rows
        results = await conn.fetch("SELECT DISTINCT session_id FROM transcripts")
        print("Current session IDs in transcripts:")
        for r in results:
            print(f" - {r['session_id']}")
            
    except Exception as e:
        print(f"Error during migration: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
