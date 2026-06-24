import asyncio
import os
import sys
import asyncpg
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hcacis.rag_engine import RAGEngine

async def build_rag_data():
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "numeric_sql_tool_v2", ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)
    else:
        load_dotenv()
        
    db_url = os.environ.get("NUMERIC_SQL_DATABASE_URL", "postgresql://app_user:app_password@localhost:54331/app_db")
    print(f"Connecting to database at: {db_url}")
    
    try:
        db_pool = await asyncpg.create_pool(db_url)
    except Exception as e:
        print(f"Failed to connect to DB: {e}")
        return

    rag = RAGEngine()
    
    # Query all turns grouped by transcript
    query = """
    SELECT t.id as transcript_id, t.session_id, ct.id as chunk_id, ct.speaker, ct.text
    FROM transcripts t
    JOIN chunks_turn ct ON t.id = ct.transcript_id
    ORDER BY t.id, ct.time_start_sec
    """
    
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(query)
    
    print(f"Found {len(rows)} dialogue chunks. Indexing into ChromaDB...")
    
    docs = []
    metadatas = []
    ids = []
    
    for row in rows:
        transcript_id = str(row['transcript_id'])
        chunk_id = str(row['chunk_id'])
        speaker = row['speaker']
        text = row['text']
        
        docs.append(f"[{speaker}]: {text}")
        metadatas.append({
            "transcript_id": transcript_id,
            "session_id": str(row['session_id']),
            "speaker": speaker
        })
        ids.append(chunk_id)
        
        # Batch insert to avoid overloading (Chroma handles small batches well)
        if len(docs) >= 100:
            embeddings = rag.embeddings.embed_documents(docs)
            rag.collection.upsert(
                documents=docs,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids
            )
            print(f"Indexed {len(docs)} documents...")
            docs, metadatas, ids = [], [], []
            
    if docs:
        embeddings = rag.embeddings.embed_documents(docs)
        rag.collection.upsert(
            documents=docs,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )
        print(f"Indexed final {len(docs)} documents.")

    await db_pool.close()
    print("Done building RAG data!")

if __name__ == "__main__":
    asyncio.run(build_rag_data())
