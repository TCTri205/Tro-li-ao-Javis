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
        await conn.execute('CREATE EXTENSION IF NOT EXISTS vector;')
        
        # Drop existing tables if they exist to start fresh
        print("Dropping existing tables if they exist...")
        await conn.execute('DROP TABLE IF EXISTS session_entity_index CASCADE;')
        await conn.execute('DROP TABLE IF EXISTS session_context_payload CASCADE;')
        await conn.execute('DROP TABLE IF EXISTS session_context_cache CASCADE;')
        await conn.execute('DROP TABLE IF EXISTS chat_history CASCADE;')

        # Create chat_history
        print("Creating table chat_history...")
        await conn.execute("""
            CREATE TABLE chat_history (
                id                BIGSERIAL PRIMARY KEY,
                session_id        VARCHAR(64) NOT NULL,
                role              VARCHAR(50) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
                content           TEXT NOT NULL,
                rewritten_content TEXT,
                answer_confidence VARCHAR(50) NOT NULL CHECK (answer_confidence IN ('high', 'medium', 'low')) DEFAULT 'high',
                routing_metadata  JSONB,
                created_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await conn.execute("""
            CREATE INDEX idx_chat_history_session_time 
            ON chat_history (session_id, created_at ASC);
        """)

        # Create session_context_cache
        print("Creating table session_context_cache...")
        await conn.execute("""
            CREATE TABLE session_context_cache (
                id                      BIGSERIAL PRIMARY KEY,
                session_id              VARCHAR(64) NOT NULL,
                topic_key               TEXT NOT NULL,
                last_pipeline           VARCHAR(50) NOT NULL CHECK (last_pipeline IN ('RAG', 'SQL', 'WEB', 'MODEL')),
                last_routing_method     VARCHAR(50) NOT NULL CHECK (last_routing_method IN ('heuristics', 'embeddings', 'llm_router', 'fallback')),
                query_embedding         vector(384),
                embedding_model_version VARCHAR(100),
                last_accessed_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                refreshed_at            TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (session_id, topic_key)
            );
        """)
        await conn.execute("""
            CREATE INDEX idx_context_cache_session_topic 
            ON session_context_cache (session_id, topic_key);
        """)
        await conn.execute("""
            CREATE INDEX idx_context_cache_last_accessed 
            ON session_context_cache (last_accessed_at);
        """)
        await conn.execute("""
            CREATE INDEX idx_context_cache_web_refreshed 
            ON session_context_cache (refreshed_at) 
            WHERE last_pipeline = 'WEB';
        """)

        # Create session_context_payload
        print("Creating table session_context_payload...")
        await conn.execute("""
            CREATE TABLE session_context_payload (
                id              BIGSERIAL PRIMARY KEY,
                cache_id        BIGINT NOT NULL REFERENCES session_context_cache(id) ON DELETE CASCADE,
                cached_payload  JSONB NOT NULL,
                summary_context JSONB,
                UNIQUE (cache_id)
            );
        """)
        await conn.execute("""
            CREATE INDEX idx_context_payload_cache_id 
            ON session_context_payload (cache_id);
        """)

        # Create session_entity_index
        print("Creating table session_entity_index...")
        await conn.execute("""
            CREATE TABLE session_entity_index (
                id              BIGSERIAL PRIMARY KEY,
                session_id      VARCHAR(64) NOT NULL,
                entity_id       TEXT NOT NULL,
                entity_type     VARCHAR(50) NOT NULL CHECK (entity_type IN ('meeting_transcript', 'person', 'document', 'sql_result')),
                display_names   TEXT[] NOT NULL,
                cache_slot_id   BIGINT REFERENCES session_context_cache(id) ON DELETE CASCADE,
                created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (session_id, entity_id)
            );
        """)
        await conn.execute("""
            CREATE INDEX idx_entity_index_display_names 
            ON session_entity_index USING gin (display_names);
        """)
        await conn.execute("""
            CREATE INDEX idx_entity_index_session_type 
            ON session_entity_index (session_id, entity_type);
        """)

        print("Database schema successfully initialized!")
        
    except Exception as e:
        print(f"Error during schema initialization: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
