import json
import logging
from datetime import datetime, timezone
from config import MAX_CACHE_SLOTS

logger = logging.getLogger(__name__)

async def get_cache_slot(conn, session_id: str, topic_key: str) -> dict:
    """
    Retrieves the cache metadata and payload for a given session and topic_key.
    """
    if topic_key:
        topic_key = topic_key.strip().strip('"').strip("'")
    row = await conn.fetchrow("""
        SELECT c.id, c.topic_key, c.last_pipeline, c.last_routing_method, c.refreshed_at, p.cached_payload, p.summary_context
        FROM session_context_cache c
        JOIN session_context_payload p ON c.id = p.cache_id
        WHERE c.session_id = $1 AND c.topic_key = $2
    """, session_id, topic_key)
    if row:
        return {
            "id": row["id"],
            "topic_key": row["topic_key"],
            "last_pipeline": row["last_pipeline"],
            "last_routing_method": row["last_routing_method"],
            "refreshed_at": row["refreshed_at"],
            "payload": json.loads(row["cached_payload"]) if row["cached_payload"] else None,
            "summary_context": json.loads(row["summary_context"]) if row["summary_context"] else None,
        }
    return None

async def touch_cache_slot(conn, session_id: str, topic_key: str):
    """
    Only updates last_accessed_at timestamp when a cache slot is hit.
    """
    if topic_key:
        topic_key = topic_key.strip().strip('"').strip("'")
    await conn.execute("""
        UPDATE session_context_cache
        SET last_accessed_at = NOW()
        WHERE session_id = $1 AND topic_key = $2
    """, session_id, topic_key)
    logger.debug(f"Touched cache slot '{topic_key}' for session {session_id}")

async def insert_cache_slot(conn, session_id: str, topic_key: str, last_pipeline: str, last_routing_method: str, payload: dict, summary_context: dict, query_embedding: list = None):
    """
    Inserts a new cache slot, performing LRU eviction if the session exceeds 3 slots.
    """
    if topic_key:
        topic_key = topic_key.strip().strip('"').strip("'")
    # Count current slots for this session
    cnt = await conn.fetchval(
        "SELECT COUNT(*) FROM session_context_cache WHERE session_id = $1", session_id
    )
    if cnt >= MAX_CACHE_SLOTS:
        # Evict the oldest one based on last_accessed_at
        await conn.execute("""
            DELETE FROM session_context_cache
            WHERE id = (
                SELECT id FROM session_context_cache
                WHERE session_id = $1
                ORDER BY last_accessed_at ASC
                LIMIT 1
            );
        """, session_id)
        logger.info(f"LRU Eviction: deleted oldest cache slot for session {session_id} because count reached {cnt}")
        
    emb_str = None
    if query_embedding:
        emb_str = "[" + ",".join(map(str, query_embedding)) + "]"
        
    cache_id = await conn.fetchval("""
        INSERT INTO session_context_cache (session_id, topic_key, last_pipeline, last_routing_method, query_embedding, embedding_model_version)
        VALUES ($1, $2, $3, $4, $5, 'multilingual-e5-small')
        RETURNING id
    """, session_id, topic_key, last_pipeline, last_routing_method, emb_str)
    
    await conn.execute("""
        INSERT INTO session_context_payload (cache_id, cached_payload, summary_context)
        VALUES ($1, $2, $3)
    """, cache_id, json.dumps(payload), json.dumps(summary_context))
    
    return cache_id

async def upsert_cache_slot(conn, session_id: str, topic_key: str, last_pipeline: str, last_routing_method: str, payload: dict, summary_context: dict, query_embedding: list = None):
    """
    Upserts a cache slot. If the slot already exists, it updates it; otherwise, it inserts it.
    """
    if topic_key:
        topic_key = topic_key.strip().strip('"').strip("'")
    row = await conn.fetchrow(
        "SELECT id FROM session_context_cache WHERE session_id = $1 AND topic_key = $2", session_id, topic_key
    )
    if row:
        cache_id = row['id']
        emb_str = None
        if query_embedding:
            emb_str = "[" + ",".join(map(str, query_embedding)) + "]"
            
        if emb_str:
            await conn.execute("""
                UPDATE session_context_cache
                SET last_pipeline = $1, last_routing_method = $2, query_embedding = $3, last_accessed_at = NOW(), refreshed_at = NOW()
                WHERE id = $4
            """, last_pipeline, last_routing_method, emb_str, cache_id)
        else:
            await conn.execute("""
                UPDATE session_context_cache
                SET last_pipeline = $1, last_routing_method = $2, last_accessed_at = NOW(), refreshed_at = NOW()
                WHERE id = $3
            """, last_pipeline, last_routing_method, cache_id)
            
        await conn.execute("""
            INSERT INTO session_context_payload (cache_id, cached_payload, summary_context)
            VALUES ($1, $2, $3)
            ON CONFLICT (cache_id)
            DO UPDATE SET cached_payload = EXCLUDED.cached_payload, summary_context = EXCLUDED.summary_context
        """, cache_id, json.dumps(payload), json.dumps(summary_context))
        
        return cache_id
    else:
        return await insert_cache_slot(conn, session_id, topic_key, last_pipeline, last_routing_method, payload, summary_context, query_embedding=query_embedding)

async def update_cache_slot(conn, session_id: str, topic_key: str, payload: dict, summary_context: dict = None, query_embedding: list = None):
    """
    Updates the payload and timestamps (and optionally query_embedding) of an existing cache slot.
    Locks the row using FOR UPDATE first to prevent concurrent transaction interference.
    """
    if topic_key:
        topic_key = topic_key.strip().strip('"').strip("'")
    # [Locking Gap 2]: Lock hot row to prevent LRU eviction from deleting it during transaction
    await conn.execute("""
        SELECT 1 FROM session_context_cache
        WHERE session_id = $1 AND topic_key = $2
        FOR UPDATE
    """, session_id, topic_key)
    
    # Get cache_id for payload insertion/update
    cache_id = await conn.fetchval("""
        SELECT id FROM session_context_cache
        WHERE session_id = $1 AND topic_key = $2
    """, session_id, topic_key)
    
    if cache_id:
        if summary_context is not None:
            await conn.execute("""
                INSERT INTO session_context_payload (cache_id, cached_payload, summary_context)
                VALUES ($1, $2, $3)
                ON CONFLICT (cache_id)
                DO UPDATE SET cached_payload = EXCLUDED.cached_payload, summary_context = EXCLUDED.summary_context
            """, cache_id, json.dumps(payload), json.dumps(summary_context))
        else:
            await conn.execute("""
                INSERT INTO session_context_payload (cache_id, cached_payload)
                VALUES ($1, $2)
                ON CONFLICT (cache_id)
                DO UPDATE SET cached_payload = EXCLUDED.cached_payload
            """, cache_id, json.dumps(payload))
        
    # Update hot table metadata
    if query_embedding:
        emb_str = "[" + ",".join(map(str, query_embedding)) + "]"
        await conn.execute("""
            UPDATE session_context_cache
            SET last_accessed_at = NOW(), refreshed_at = NOW(), query_embedding = $1
            WHERE session_id = $2 AND topic_key = $3
        """, emb_str, session_id, topic_key)
    else:
        await conn.execute("""
            UPDATE session_context_cache
            SET last_accessed_at = NOW(), refreshed_at = NOW()
            WHERE session_id = $1 AND topic_key = $2
        """, session_id, topic_key)

def check_cache_ttl(refreshed_at: datetime, ttl_seconds: int = 3600) -> bool:
    """
    Verifies if a cache slot is still fresh based on its refreshed_at timestamp.
    """
    if not refreshed_at:
        return False
    
    # Ensure timezone aware comparison
    now = datetime.now(timezone.utc)
    if refreshed_at.tzinfo is None:
        refreshed_at = refreshed_at.replace(tzinfo=timezone.utc)
    
    age_seconds = (now - refreshed_at).total_seconds()
    return age_seconds <= ttl_seconds
