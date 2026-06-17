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
        # Enable extensions
        print("Enabling extensions...")
        await conn.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
        
        # Create transcripts
        print("Creating table transcripts...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS transcripts (
                id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                session_id        VARCHAR(64) NOT NULL,
                meeting_date      DATE,
                participants      JSONB,
                speaker_count     INT,
                duration_seconds  INT,
                raw_text          TEXT,
                summary           TEXT
            );
        """)

        # Create chunks_turn
        print("Creating table chunks_turn...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks_turn (
                id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                transcript_id     UUID REFERENCES transcripts(id) ON DELETE CASCADE,
                turn_index        INT,
                speaker           VARCHAR(255),
                time_start_sec    INT,
                time_end_sec      INT,
                text              TEXT
            );
        """)

        # Create company_chunks
        print("Creating table company_chunks...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS company_chunks (
                id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                document_id       UUID,
                text              TEXT,
                metadata          JSONB
            );
        """)

        print("Extra tables successfully initialized!")
        
    except Exception as e:
        print(f"Error during extra tables initialization: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
