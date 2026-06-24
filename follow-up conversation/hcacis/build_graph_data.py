import asyncio
import os
import sys
import asyncpg
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hcacis.context_graph import ContextGraph
from hcacis.models import Entity

async def build_graph_data():
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "numeric_sql_tool_v2", ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)
    else:
        load_dotenv()
        
    db_url = os.environ.get("NUMERIC_SQL_DATABASE_URL", "postgresql://app_user:app_password@localhost:54331/app_db")
    print(f"Connecting to Postgres at: {db_url}")
    
    try:
        db_pool = await asyncpg.create_pool(db_url)
    except Exception as e:
        print(f"Failed to connect to Postgres: {e}")
        return

    graph = ContextGraph()
    if not graph.is_connected:
        print("Neo4j is not connected. Please make sure Neo4j Desktop is running at bolt://localhost:7687")
        return

    print("Clearing existing Graph DB...")
    with graph.driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")

    print("Fetching Users (Speakers) from Postgres...")
    async with db_pool.acquire() as conn:
        speakers = await conn.fetch("SELECT DISTINCT speaker FROM chunks_turn WHERE speaker IS NOT NULL")
        for s in speakers:
            s_name = s['speaker']
            ent = Entity(
                id=f"user_{s_name}",
                type="Person",
                name=s_name,
                attributes={"role": "speaker"}
            )
            graph.add_entity(ent)
        print(f"Added {len(speakers)} users to Graph DB.")

        print("Fetching Meetings (Transcripts) from Postgres...")
        transcripts = await conn.fetch("SELECT id, session_id, meeting_date, status FROM transcripts")
        for t in transcripts:
            tid = str(t['id'])
            # Create Meeting Entity
            ent = Entity(
                id=f"meeting_{tid}",
                type="Meeting",
                name=f"Meeting {t['session_id']}",
                attributes={"meeting_date": str(t['meeting_date']), "status": t['status']}
            )
            graph.add_entity(ent)
            
            # Find who attended this specific meeting
            meeting_speakers = await conn.fetch("SELECT DISTINCT speaker FROM chunks_turn WHERE transcript_id = $1 AND speaker IS NOT NULL", t['id'])
            
            for ms in meeting_speakers:
                ms_name = ms['speaker']
                graph.add_relation(f"user_{ms_name}", f"meeting_{tid}", "ATTENDED")
                
        print(f"Added {len(transcripts)} meetings and attendance relationships to Graph DB.")

    graph.close()
    print("Done building Graph DB!")

if __name__ == "__main__":
    asyncio.run(build_graph_data())
