import json
import logging
from datetime import datetime, timezone
from config import (
    MAX_CACHE_SLOTS,
    EMBEDDING_MODEL_VERSION,
    EMA_ALPHA,
    EMA_MAX_UPDATES,
    EMA_DISTANCE_THRESHOLD,
    EMA_SIMID_SAFEGUARD
)

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
    Inserts a new cache slot, performing LRU eviction if the session exceeds MAX_CACHE_SLOTS slots.
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
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id
    """, session_id, topic_key, last_pipeline, last_routing_method, emb_str, EMBEDDING_MODEL_VERSION)
    
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


async def update_cache_slot_ema(conn, session_id: str, topic_key: str, query_embedding: list):
    """
    ponytail: Updates the representative query embedding of a cache slot using EMA.
    Formula: V_new = alpha * V_current + (1 - alpha) * V_query with alpha = 0.8.
    Applies drift mitigation and similarity safeguards.
    """
    if not query_embedding:
        return
        
    if topic_key:
        topic_key = topic_key.strip().strip('"').strip("'")
        
    # Fetch current embedding (as text) and summary_context
    row = await conn.fetchrow("""
        SELECT c.id, c.query_embedding::text as query_embedding_str, p.summary_context
        FROM session_context_cache c
        LEFT JOIN session_context_payload p ON c.id = p.cache_id
        WHERE c.session_id = $1 AND c.topic_key = $2
    """, session_id, topic_key)
    
    if not row:
        return
        
    cache_id = row['id']
    current_emb_str = row['query_embedding_str']
    summary_context = json.loads(row['summary_context']) if row['summary_context'] else {}
    
    import numpy as np
    
    # Get current embedding
    if current_emb_str:
        try:
            V_current = np.array(json.loads(current_emb_str))
        except Exception:
            V_current = None
    else:
        V_current = None
        
    V_query = np.array(query_embedding)
    
    # 1. Store original embedding if not already present
    original_emb_list = summary_context.get("original_query_embedding")
    if not original_emb_list:
        if V_current is not None:
            summary_context["original_query_embedding"] = V_current.tolist()
            V_orig = V_current
        else:
            summary_context["original_query_embedding"] = V_query.tolist()
            V_orig = V_query
    else:
        V_orig = np.array(original_emb_list)
        
    # 2. Check update count
    update_count = summary_context.get("ema_update_count", 0)
    
    if update_count >= EMA_MAX_UPDATES:
        # Vector is locked, do not update the vector but we can update summary_context
        logger.info(f"EMA Update: Vector for slot '{topic_key}' is locked (count={update_count}).")
        return
        
    # 3. Calculate distance between V_query and V_current
    if V_current is not None:
        # Cosine distance = 1 - Cosine similarity
        norm_curr = np.linalg.norm(V_current)
        norm_q = np.linalg.norm(V_query)
        if norm_curr > 0 and norm_q > 0:
            cos_dist = 1.0 - (np.dot(V_current, V_query) / (norm_curr * norm_q))
        else:
            cos_dist = 0.0
            
        if cos_dist > EMA_DISTANCE_THRESHOLD:
            # Bypass EMA update to force Tier 2 routing in subsequent turns if needed
            logger.info(f"EMA Update: Distance ({cos_dist:.4f}) > {EMA_DISTANCE_THRESHOLD}, bypassing EMA update.")
            return
            
        # Compute EMA
        V_new = EMA_ALPHA * V_current + (1.0 - EMA_ALPHA) * V_query
        # Normalize V_new
        norm_new = np.linalg.norm(V_new)
        if norm_new > 0:
            V_new /= norm_new
    else:
        V_new = V_query
        
    # 4. Check absolute similarity bound with V_orig
    if V_orig is not None:
        norm_new = np.linalg.norm(V_new)
        norm_orig = np.linalg.norm(V_orig)
        if norm_new > 0 and norm_orig > 0:
            orig_similarity = np.dot(V_new, V_orig) / (norm_new * norm_orig)
        else:
            orig_similarity = 1.0
            
        if orig_similarity < EMA_SIMID_SAFEGUARD:
            logger.info(f"EMA Update: Similarity with original vector ({orig_similarity:.4f}) < {EMA_SIMID_SAFEGUARD}. Resetting to original vector.")
            V_new = V_orig
            update_count = 0
        else:
            update_count += 1
    else:
        update_count += 1
        
    # Save the updated embedding and count
    summary_context["ema_update_count"] = update_count
    
    # Update query_embedding and summary_context in the DB
    emb_str = "[" + ",".join(map(str, V_new.tolist())) + "]"
    await conn.execute("""
        UPDATE session_context_cache
        SET query_embedding = $1::vector, last_accessed_at = NOW(), refreshed_at = NOW()
        WHERE id = $2
    """, emb_str, cache_id)
    
    await conn.execute("""
        UPDATE session_context_payload
        SET summary_context = $1
        WHERE cache_id = $2
    """, json.dumps(summary_context), cache_id)
    
    logger.info(f"EMA Update success for slot '{topic_key}': update_count={update_count}")
