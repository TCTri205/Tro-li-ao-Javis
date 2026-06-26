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
        print("Checking/adding attributes column to session_entity_index...")
        await conn.execute("""
            ALTER TABLE session_entity_index 
            ADD COLUMN IF NOT EXISTS attributes JSONB DEFAULT '{}'::jsonb;
        """)
        print("Migration completed successfully!")
    except Exception as e:
        print(f"Error during migration: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
