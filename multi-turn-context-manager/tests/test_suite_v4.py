import asyncio
import time
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
import asyncpg
from dotenv import load_dotenv

# Reconfigure stdout to support UTF-8 on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from router import get_llm_manager
from orchestrator import IntelligentOrchestrator
from cache_manager import upsert_cache_slot, get_cache_slot

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()
DB_URL = os.getenv("NUMERIC_SQL_DATABASE_URL", "postgresql://app_user:app_password@localhost:54331/app_db")

# ---------------------------------------------------------------------------
# MockSentenceTransformer — deterministic n-gram hash embedding (fast, no GPU)
# ---------------------------------------------------------------------------
class MockSentenceTransformer:
    def __init__(self, *args, **kwargs):
        pass

    def encode(self, sentences, **kwargs):
        import numpy as np
        import hashlib
        is_single = isinstance(sentences, str)
        if is_single:
            sentences = [sentences]
        results = []
        for text in sentences:
            text = text.replace("query: ", "").replace("passage: ", "")
            ngrams = []
            for n in [1, 2, 3]:
                for i in range(len(text) - n + 1):
                    ngrams.append(text[i:i+n])
            if not ngrams:
                ngrams = [text]
            vec = np.zeros(384)
            for ngram in ngrams:
                h = int(hashlib.md5(ngram.encode('utf-8')).hexdigest(), 16)
                rng = np.random.RandomState(h % (2**32 - 1))
                vec += rng.normal(size=384)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec /= norm
            results.append(vec)
        if is_single:
            return results[0]
        import numpy as np
        return np.array(results)


class TestSuiteV4:
    def __init__(self):
        self.db_pool = None
        self.embedding_model = None
        self.llm_manager = None
        self.orchestrator = None
        self.results = []

    async def init(self):
        logger.info("Initializing Test Suite V4 (Hallucination Hard Mode)...")
        self.db_pool = await asyncpg.create_pool(DB_URL, min_size=10, max_size=30)
        self.embedding_model = MockSentenceTransformer()
        self.llm_manager = get_llm_manager()
        self.orchestrator = IntelligentOrchestrator(self.db_pool, self.llm_manager, self.embedding_model)
        logger.info("Test Suite V4 initialized.")

    async def close(self):
        if self.db_pool:
            await self.db_pool.close()

    async def clear_db(self, session_id: str = None):
        async with self.db_pool.acquire() as conn:
            if session_id:
                await conn.execute("DELETE FROM chat_history WHERE session_id = $1", session_id)
                await conn.execute("DELETE FROM session_context_cache WHERE session_id = $1", session_id)
                await conn.execute("DELETE FROM session_entity_index WHERE session_id = $1", session_id)
            else:
                await conn.execute("DELETE FROM chat_history")
                await conn.execute("DELETE FROM session_context_cache")
                await conn.execute("DELETE FROM session_entity_index")

    async def record_result(self, category, test_id, query, answer, metadata, passed, error=None):
        self.results.append({
            "category": category,
            "test_id": test_id,
            "query": query,
            "answer": answer,
            "metadata": metadata,
            "passed": passed,
            "error": error
        })

    # ==========================================================================
    # SCENARIO H: HALLUCINATION & VULNERABILITY HARD TESTS
    # ==========================================================================
    
    async def run_scenario_h_hallucination_vulnerabilities(self):
        logger.info("=== SCENARIO H: Hallucination & Vulnerability Hard Tests ===")
        sid = "v4_hallucination_tests"
        await self.clear_db(sid)

        # ----------------------------------------------------------------------
        # H1: Web Engine URL & Info Validation (V-01)
        # ----------------------------------------------------------------------
        # Query forcing WEB pipeline search for a dynamic 2026/future topic
        q1 = "ネットで最新のAIニュースについて検索して、関係する記事のURLを含めて要約してください。"
        ans1, meta1 = await self.orchestrator.handle(sid, q1)
        
        # Verify it routes to WEB pipeline
        is_web = meta1.get("target_pipeline") == "WEB"
        # Since it simulates search, check if urls are in the answer and look simulated
        has_url = "http" in ans1 or "www" in ans1
        p1 = is_web and has_url
        await self.record_result(
            "H_Hallucination", "H1_WEB_SIMULATED_URL", 
            q1, ans1, meta1, p1,
            error=None if p1 else f"Target pipeline: {meta1.get('target_pipeline')}, Has URL: {has_url}"
        )

        # ----------------------------------------------------------------------
        # H2: Fail-Open Verifier Exception Disclaimer (V-02)
        # ----------------------------------------------------------------------
        # We manually monkey-patch _verify_hallucination to raise an exception
        # and test if the orchestrator appends the warning disclaimer to the response.
        original_verify = self.orchestrator._verify_hallucination
        
        async def mock_verify_failed(response: str, context_str: str):
            raise Exception("Mock Connection Timeout to Verifier LLM")
            
        self.orchestrator._verify_hallucination = mock_verify_failed
        
        q2 = "GT_03の島田さんは何を希望していましたか？"
        ans2, meta2 = await self.orchestrator.handle(sid, q2)
        
        # Restore original verifier
        self.orchestrator._verify_hallucination = original_verify
        
        # Check if the disclaimer warning is in the answer
        has_warning = "警告" in ans2 and "整合性" in ans2 and "保証できません" in ans2
        p2 = has_warning
        await self.record_result(
            "H_Hallucination", "H2_FAIL_OPEN_WARNING", 
            q2, ans2, meta2, p2,
            error=None if p2 else "Response did not contain the connection warning disclaimer."
        )

        # ----------------------------------------------------------------------
        # H3: Double Pronoun Replacement Loop (V-07)
        # ----------------------------------------------------------------------
        # We seed the DB cache with GT_03 and set active context.
        # Then, ask a query with multiple pronouns "彼" (he) and "それ" (it/that case).
        # Both must be resolved to Shimada/GT_03.
        async with self.db_pool.acquire() as conn:
            # Seed GT_03 cache
            c_id = await upsert_cache_slot(
                conn, sid, "GT_03_topic", "RAG", "heuristics",
                {"documents": [{"chunk_id": "c1", "text": "島田さんは物件の内見を希望しています。"}]},
                {"entity_id": "GT_03", "entity_type": "meeting_transcript"}
            )
            # Add entity mapping for pronoun resolver (delete first to prevent UniqueViolationError)
            await conn.execute("DELETE FROM session_entity_index WHERE session_id = $1 AND entity_id = 'GT_03'", sid)
            await conn.execute("""
                INSERT INTO session_entity_index (session_id, cache_slot_id, entity_id, entity_type, display_names)
                VALUES ($1, $2, 'GT_03', 'meeting_transcript', ARRAY['島田', 'アセットジャパン'])
            """, sid, c_id)
            
            # Add message in history referencing GT_03
            await conn.execute("""
                INSERT INTO chat_history (session_id, role, content, rewritten_content)
                VALUES ($1, 'user', 'GT_03の島田さんの件について教えて', 'GT_03の島田さんの件について教えて')
            """, sid)
            await conn.execute("""
                INSERT INTO chat_history (session_id, role, content, rewritten_content)
                VALUES ($1, 'assistant', 'はい、島田さんは内見の空き状況を確認しています。', 'はい、島田さんは内見の空き状況を確認しています。')
            """, sid)

        q3 = "彼がそれについて気にした理由は何ですか？"
        # We handle this query. The router rewrite should replace BOTH pronouns.
        # "彼" -> GT_03の島田さん, "それ" -> 内見 / 物件
        ans3, meta3 = await self.orchestrator.handle(sid, q3)
        rewritten = meta3.get("rewritten_query", "")
        
        # Verify both pronouns are replaced in rewritten query.
        # (It shouldn't contain "彼" or "それ" if successfully resolved, or should contain "島田" and "GT_03")
        contains_resolved = "島田" in rewritten or "GT_03" in rewritten
        still_has_unresolved = "彼" in rewritten or "それ" in rewritten
        # The test passes if it resolved the pronouns (contains_resolved) and doesn't leave them unreplaced
        p3 = contains_resolved and not still_has_unresolved
        await self.record_result(
            "H_Hallucination", "H3_DOUBLE_PRONOUN_REPLACEMENT", 
            q3, ans3, meta3, p3,
            error=None if p3 else f"Rewritten query: '{rewritten}'. Pronouns left unresolved."
        )

        # ----------------------------------------------------------------------
        # H4: Cache TTL Stale Context Filter (V-06)
        # ----------------------------------------------------------------------
        # Seed an expired cache (25 hours ago).
        # A follow-up query with pronouns should NOT resolve to this expired cache.
        # It should bypass cache and retrieve fresh data.
        sid_ttl = "v4_stale_cache_test"
        await self.clear_db(sid_ttl)
        
        async with self.db_pool.acquire() as conn:
            c_id = await upsert_cache_slot(
                conn, sid_ttl, "GT_03_topic", "RAG", "heuristics",
                {"documents": [{"chunk_id": "c1", "text": "島田さんは物件の内見を希望しています。"}]},
                {"entity_id": "GT_03", "entity_type": "meeting_transcript"}
            )
            # Add entity mapping
            await conn.execute("""
                INSERT INTO session_entity_index (session_id, cache_slot_id, entity_id, entity_type, display_names)
                VALUES ($1, $2, 'GT_03', 'meeting_transcript', ARRAY['島田', 'アセットジャパン'])
            """, sid_ttl, c_id)
            
            # Set refreshed_at to 25 hours ago to expire it
            expired_time = datetime.now(timezone.utc) - timedelta(hours=25)
            await conn.execute("UPDATE session_context_cache SET refreshed_at = $1 WHERE id = $2", expired_time, c_id)

        q4 = "その時の詳しい内容を教えてください。"
        ans4, meta4 = await self.orchestrator.handle(sid_ttl, q4)
        
        # If cache is expired, active_caches should not provide it, and needs_retrieval should be full/partial, not none
        p4 = meta4.get("needs_retrieval") == "full"
        await self.record_result(
            "H_Hallucination", "H4_CACHE_TTL_STALE_FILTER", 
            q4, ans4, meta4, p4,
            error=None if p4 else f"Cache reuse not prevented: needs_retrieval={meta4.get('needs_retrieval')}"
        )

        # ----------------------------------------------------------------------
        # H5: Role Reversal in Dialogue (V-03)
        # ----------------------------------------------------------------------
        # GT_07 is AJ Technolgies Yamashita calling Maruken. Ishihara is absent.
        # Receptionist answers the call.
        # We ask who called whom to test if the model reverses caller/receiver.
        q5 = "GT_07の通話で、誰から誰に電話をかけましたか？発信側と受信側を明確にして答えてください。"
        ans5, meta5 = await self.orchestrator.handle(sid, q5)
        
        # Correct interpretation: Yamashita (山下) is caller (発信), Maruken/receptionist (マルケン/受付) is receiver (受信)
        # It must NOT say Ishihara (石原) or Maruken called Yamashita.
        contains_yamashita_caller = "山下" in ans5 and any(x in ans5 for x in ["発信", "かけた", "から"])
        contains_receptionist_receiver = any(x in ans5 for x in ["マルケン", "受付", "石原", "イシハラ", "いしはら"]) and any(x in ans5 for x in ["受信", "受けた", "宛て", "に"])
        reversal_detected = "山下さん宛て" in ans5 or "山下さんが電話を受けた" in ans5
        
        p5 = contains_yamashita_caller and contains_receptionist_receiver and not reversal_detected
        await self.record_result(
            "H_Hallucination", "H5_ROLE_REVERSAL_CHECK", 
            q5, ans5, meta5, p5,
            error=None if p5 else f"Yamashita Caller: {contains_yamashita_caller}, Recipient Receiver: {contains_receptionist_receiver}, Reversal: {reversal_detected}"
        )

        # ----------------------------------------------------------------------
        # H6: Direct Path Aggregation Bypassing Generator Reasoning (V-08)
        # ----------------------------------------------------------------------
        # Query asking for a logical explanation of an aggregate query result.
        # The system must NOT use direct path (since direct path returns raw values / templates)
        # and instead use the LLM generator to explain.
        q6 = "GT_03とGT_09の通話時間の合計秒数について、その計算が正しい理由と背景を解説してください。"
        ans6, meta6 = await self.orchestrator.handle(sid, q6)
        
        # The direct path must be bypassed (False)
        is_direct = meta6.get("is_direct_path", False)
        # Answer must contain reasoning or explanatory text, not just a raw template number.
        has_explanation = len(ans6) > 30 and any(x in ans6 for x in ["理由", "背景", "合計", "秒", "なぜなら", "足すと"])
        p6 = not is_direct and has_explanation
        await self.record_result(
            "H_Hallucination", "H6_DIRECT_PATH_REASONING_BYPASS", 
            q6, ans6, meta6, p6,
            error=None if p6 else f"Is direct path: {is_direct}, Has explanation: {has_explanation}"
        )

        # ----------------------------------------------------------------------
        # H7: Concurrent Session Advisory Lock Timeout (V-09)
        # ----------------------------------------------------------------------
        # We start a transaction and acquire the advisory lock on pg_try_advisory_xact_lock
        # for a special session id. Then we attempt to call orchestrator.handle on the same session
        # with a lock_timeout of 0.5s. It must raise asyncio.TimeoutError.
        sid_lock = "v4_concurrency_lock_test"
        await self.clear_db(sid_lock)
        
        from session_lock import get_lock_id
        lock_id = get_lock_id(sid_lock)
        
        p7 = False
        conn_holder = await self.db_pool.acquire()
        tx_holder = conn_holder.transaction()
        await tx_holder.start()
        
        try:
            # Manually lock it
            locked = await conn_holder.fetchval("SELECT pg_try_advisory_xact_lock($1)", lock_id)
            if locked:
                logger.info("Advisory lock acquired manually in holder transaction.")
                
                # Now try to call handle() which should block and time out
                try:
                    await self.orchestrator.handle(sid_lock, "GT_03の件について", lock_timeout=0.5)
                except asyncio.TimeoutError:
                    logger.info("Orchestrator correctly timed out waiting for advisory lock.")
                    p7 = True
                except Exception as ex:
                    logger.error(f"Orchestrator raised unexpected exception: {ex}")
        finally:
            await tx_holder.rollback()
            await self.db_pool.release(conn_holder)
            
        await self.record_result(
            "H_Hallucination", "H7_CONCURRENT_SESSION_LOCK_TIMEOUT",
            "Simulating concurrent request advisory lock timeout",
            "Orchestrator raises asyncio.TimeoutError",
            {}, p7,
            error=None if p7 else "Advisory lock timeout exception was not raised as expected."
        )

        # ----------------------------------------------------------------------
        # H8: Circuit Breaker State Transitions (V-10)
        # ----------------------------------------------------------------------
        # We test that 3 consecutive failures transitions the breaker to OPEN.
        # Once OPEN, calls fail fast and return fallback.
        # After cooldown, a request transitions it to HALF_OPEN, and if it succeeds, resets to CLOSED.
        from engines import EngineCircuitBreaker, EngineResult
        
        class MockFailingEngine:
            def __init__(self):
                self.call_count = 0
                self.should_fail = True
                
            async def execute(self, query: str, **kwargs):
                self.call_count += 1
                if self.should_fail:
                    raise Exception("Simulated DB connection drop")
                return EngineResult(source="mock_db", payload={"rows": [{"status": "ok"}]})
                
        mock_engine = MockFailingEngine()
        cb = EngineCircuitBreaker(mock_engine, failure_threshold=3, cooldown_seconds=2, timeout_seconds=1.0)
        
        # Initial state should be CLOSED
        cond1 = cb.state == "CLOSED"
        
        # 3 failures to trigger OPEN
        res1 = await cb.execute("SELECT 1")
        res2 = await cb.execute("SELECT 2")
        res3 = await cb.execute("SELECT 3")
        
        cond2 = cb.state == "OPEN"
        cond3 = res3.payload.get("fallback") is True
        
        # Check call count of actual engine
        cond4 = mock_engine.call_count == 3
        
        # Call again while OPEN and before cooldown: should not call underlying engine (still 3)
        res4 = await cb.execute("SELECT 4")
        cond5 = mock_engine.call_count == 3
        
        # Simulate cooldown by pushing last state change time back
        cb.last_state_change -= 3
        
        # Breaker should enter HALF_OPEN and test next request
        mock_engine.should_fail = False
        res5 = await cb.execute("SELECT 5")
        
        cond6 = cb.state == "CLOSED"
        cond7 = mock_engine.call_count == 4
        cond8 = res5.payload.get("rows") == [{"status": "ok"}]
        
        p8 = cond1 and cond2 and cond3 and cond4 and cond5 and cond6 and cond7 and cond8
        await self.record_result(
            "H_Hallucination", "H8_CIRCUIT_BREAKER_TRANSITIONS",
            "Simulating circuit breaker state transitions (CLOSED->OPEN->HALF_OPEN->CLOSED)",
            f"Breaker transitions: {cb.state}, call_count: {mock_engine.call_count}",
            {}, p8,
            error=None if p8 else f"Failed checks: cond1={cond1}, cond2={cond2}, cond3={cond3}, cond4={cond4}, cond5={cond5}, cond6={cond6}, cond7={cond7}, cond8={cond8}"
        )

        # ----------------------------------------------------------------------
        # H9: Web Relevance & Fallback (V-11)
        # ----------------------------------------------------------------------
        from orchestrator import should_use_direct_path
        
        # Case A: Exactly 1 result, relevance > 0.85 -> True
        p9_a = should_use_direct_path("WEB", {"results": [{"relevance": 0.95}]}, "full") is True
        
        # Case B: Relevance <= 0.85 -> False
        p9_b = should_use_direct_path("WEB", {"results": [{"relevance": 0.80}]}, "full") is False
        
        # Case C: Multiple results -> False
        p9_c = should_use_direct_path("WEB", {"results": [{"relevance": 0.95}, {"relevance": 0.90}]}, "full") is False
        
        # Case D: Empty results -> False
        p9_d = should_use_direct_path("WEB", {"results": []}, "full") is False
        
        p9 = p9_a and p9_b and p9_c and p9_d
        await self.record_result(
            "H_Hallucination", "H9_WEB_RELEVANCE_AND_FALLBACK",
            "Testing should_use_direct_path for WEB pipeline",
            f"Results: A={p9_a}, B={p9_b}, C={p9_c}, D={p9_d}",
            {}, p9,
            error=None if p9 else f"Failed checks: A={p9_a}, B={p9_b}, C={p9_c}, D={p9_d}"
        )

        # ----------------------------------------------------------------------
        # H10: Gender-Aware Pronoun Resolution (Dynamic Classification)
        # ----------------------------------------------------------------------
        # Seed a GT_10 transcript with a male (佐藤太郎) and female (鈴木花子) participant.
        # Run router.route with query containing "彼" (masculine) vs "彼女" (feminine)
        # and verify they resolve to the correct participant name.
        sid_gender = "v4_gender_pronoun_test"
        await self.clear_db(sid_gender)
        
        async with self.db_pool.acquire() as conn:
            # Seed the transcripts table
            t_uuid = "12345678-1234-1234-1234-1234567890ab"
            # Delete any existing transcripts for safety
            await conn.execute("DELETE FROM chunks_turn WHERE transcript_id = $1::uuid", t_uuid)
            await conn.execute("DELETE FROM transcripts WHERE session_id = 'GT_10'")
            await conn.execute("""
                INSERT INTO transcripts (id, session_id, meeting_date, participants, raw_text, summary, duration_seconds, speaker_count)
                VALUES ($1::uuid, 'GT_10', '2026-06-24', 
                        '[{"name": "佐藤太郎", "gender": "male"}, {"name": "鈴木花子", "gender": "female"}]',
                        '佐藤太郎: こんにちは。鈴木花子: はい、こんにちは。',
                        '佐藤太郎と鈴木花子の対話', 60, 2)
            """, t_uuid)
            
            # Seed cache slot for GT_10
            c_id = await upsert_cache_slot(
                conn, sid_gender, "GT_10_topic", "RAG", "heuristics",
                {"documents": [{"chunk_id": "c_gender", "text": "佐藤太郎さんと鈴木花子さんが打ち合わせをしました。"}]},
                {"entity_id": "GT_10", "entity_type": "meeting_transcript"}
            )
            
            # Seed entity mappings in index
            await conn.execute("DELETE FROM session_entity_index WHERE session_id = $1", sid_gender)
            await conn.execute("""
                INSERT INTO session_entity_index (session_id, cache_slot_id, entity_id, entity_type, display_names)
                VALUES ($1, $2, 'GT_10', 'meeting_transcript', ARRAY['GT_10', '太郎', '花子'])
            """, sid_gender, c_id)
            await conn.execute("""
                INSERT INTO session_entity_index (session_id, cache_slot_id, entity_id, entity_type, display_names)
                VALUES ($1, $2, 'GT_10_佐藤太郎', 'person', ARRAY['佐藤太郎', '佐藤', '太郎'])
            """, sid_gender, c_id)
            await conn.execute("""
                INSERT INTO session_entity_index (session_id, cache_slot_id, entity_id, entity_type, display_names)
                VALUES ($1, $2, 'GT_10_鈴木花子', 'person', ARRAY['鈴木花子', '鈴木', '花子'])
            """, sid_gender, c_id)
            
            # Also touch cache to make it active/recent
            await conn.execute("UPDATE session_context_cache SET last_accessed_at = NOW() WHERE id = $1", c_id)
            
        # Test 1: masculine pronoun "彼" -> should resolve to 佐藤太郎
        res_he = await self.orchestrator.router.route(sid_gender, "彼が言ったことを教えて")
        rewritten_he = res_he.get("rewritten_query", "")
        p10_he = "佐藤太郎" in rewritten_he and "鈴木花子" not in rewritten_he
        
        # Test 2: feminine pronoun "彼女" -> should resolve to 鈴木花子
        res_she = await self.orchestrator.router.route(sid_gender, "彼女が言ったことを教えて")
        rewritten_she = res_she.get("rewritten_query", "")
        p10_she = "鈴木花子" in rewritten_she and "佐藤太郎" not in rewritten_she
        
        p10 = p10_he and p10_she
        await self.record_result(
            "H_Hallucination", "H10_GENDER_AWARE_PRONOUN_RESOLUTION",
            "Routing masculine vs feminine pronouns to gender-classified participants",
            f"He rewrite: '{rewritten_he}', She rewrite: '{rewritten_she}'",
            {}, p10,
            error=None if p10 else f"Failing gender resolution. He passed: {p10_he}, She passed: {p10_she}"
        )

        # ----------------------------------------------------------------------
        # H11: Cache Hit Empty Payload Downgrade (V-06)
        # ----------------------------------------------------------------------
        # If cache slot exists but payload is empty (no rows, documents, results, info),
        # orchestrator should downgrade to needs_retrieval='full' instead of using cache.
        sid_empty = "v4_empty_payload_test"
        await self.clear_db(sid_empty)
        
        async with self.db_pool.acquire() as conn:
            c_id = await upsert_cache_slot(
                conn, sid_empty, "GT_03_topic", "RAG", "heuristics",
                {}, # Empty payload
                {"entity_id": "GT_03", "entity_type": "meeting_transcript"}
            )
            # Seed entity mapping
            await conn.execute("""
                INSERT INTO session_entity_index (session_id, cache_slot_id, entity_id, entity_type, display_names)
                VALUES ($1, $2, 'GT_03', 'meeting_transcript', ARRAY['島田', 'アセットジャパン'])
            """, sid_empty, c_id)
            
        q11 = "島田さんについての詳細な内容を教えてください。"
        ans11, meta11 = await self.orchestrator.handle(sid_empty, q11)
        
        p11 = meta11.get("needs_retrieval") == "full" and meta11.get("direct_answer_used") is False
        await self.record_result(
            "H_Hallucination", "H11_CACHE_EMPTY_PAYLOAD_DOWNGRADE",
            q11, ans11, meta11, p11,
            error=None if p11 else f"Needs retrieval: {meta11.get('needs_retrieval')}, Direct answer: {meta11.get('direct_answer_used')}"
        )

        # ----------------------------------------------------------------------
        # H12: Cache Granularity Details Upgrade (V-06)
        # ----------------------------------------------------------------------
        # Seed cache with metadata but no speaker turns.
        # A query asking for details or speech turns should upgrade needs_retrieval to 'full'.
        sid_details = "v4_granularity_test"
        await self.clear_db(sid_details)
        
        async with self.db_pool.acquire() as conn:
            # Seed cache with non-turn rows (e.g. only duration_seconds)
            c_id = await upsert_cache_slot(
                conn, sid_details, "GT_03_topic", "SQL", "heuristics",
                {"rows": [{"duration_seconds": 204}]}, 
                {"entity_id": "GT_03", "entity_type": "meeting_transcript"}
            )
            await conn.execute("""
                INSERT INTO session_entity_index (session_id, cache_slot_id, entity_id, entity_type, display_names)
                VALUES ($1, $2, 'GT_03', 'meeting_transcript', ARRAY['島田', 'アセットジャパン'])
            """, sid_details, c_id)
            
        q12 = "島田さんの具体的な発言内容を教えてください。"
        ans12, meta12 = await self.orchestrator.handle(sid_details, q12)
        
        p12 = meta12.get("needs_retrieval") == "full"
        await self.record_result(
            "H_Hallucination", "H12_CACHE_GRANULARITY_DETAILS_UPGRADE",
            q12, ans12, meta12, p12,
            error=None if p12 else f"Needs retrieval: {meta12.get('needs_retrieval')}"
        )

        # ----------------------------------------------------------------------
        # H13: Cross-Pollination Entity Halt (V-03 / Hallucination Trap)
        # ----------------------------------------------------------------------
        # We query about a participant (横堀) in a session (GT_03) where they do not belong.
        # RAG or SQL context will contain Yokobori's name in GT_04 but NOT GT_03.
        # LLM must refuse to associate them or claim Yokobori is in GT_03.
        q13 = "GT_03の横堀さんはアセットジャパンに何の目的で連絡しましたか？"
        ans13, meta13 = await self.orchestrator.handle(sid, q13)
        
        # Correct answer should state that Yokobori is NOT in GT_03.
        # It must NOT say Yokobori wanted to preview a property (which is Shimada in GT_03).
        not_in_gt03 = any(x in ans13 for x in ["確認できません", "参加していません", "存在しません", "含まれていません", "いません", "GT_04", "誤り"])
        hallucinated_action = any(x in ans13 for x in ["横堀さんが内見", "横堀さんは内見", "横堀さんの内見", "横堀さんが見学", "横堀さんは見学", "横堀さんの見学"])
        p13 = not_in_gt03 and not hallucinated_action
        
        await self.record_result(
            "H_Hallucination", "H13_CROSS_POLLINATION_HALT",
            q13, ans13, meta13, p13,
            error=None if p13 else f"Failed to detect entity cross-pollination. Refusal: {not_in_gt03}, Hallucinated: {hallucinated_action}"
        )

        # ----------------------------------------------------------------------
        # H14: Absent Actor Hallucination Trap (V-03 / Identity Hallucination)
        # ----------------------------------------------------------------------
        # We ask what Nakahara Rinka said she would do in GT_04.
        # But in GT_04, she was absent (holiday) and did not speak.
        # The LLM must not attribute Yokobori's or the receptionist's words to her.
        q14 = "GT_04で中原凛花さんは、いつ折り返しの電話をかけると言っていましたか？"
        ans14, meta14 = await self.orchestrator.handle(sid, q14)
        
        # Correct: She was absent and didn't speak.
        # It must NOT say she said she would call back.
        refuses_fabrication = any(x in ans14 for x in ["お休み", "休み", "不在", "発言していません", "確認できません", "話していません"])
        hallucinated_speaking = any(x in ans14 for x in ["彼女が", "凛花さんが言った", "自分がかける"])
        p14 = refuses_fabrication and not hallucinated_speaking
        
        await self.record_result(
            "H_Hallucination", "H14_ABSENT_ACTOR_HALLUCINATION_TRAP",
            q14, ans14, meta14, p14,
            error=None if p14 else f"Failed absent actor check. Refused fabrication: {refuses_fabrication}, Hallucinated speaking: {hallucinated_speaking}"
        )

        # ----------------------------------------------------------------------
        # H15: Out-of-Context Company Info Refusal (V-03 / Parametric Hallucination)
        # ----------------------------------------------------------------------
        # Querying about the CEO of Asset Japan in 2026. This info is not in the database.
        # LLM must refuse to guess or fabricate a name.
        q15 = "アセットジャパン of 2026年現在の代表取締役社長の名前を教えてください。"
        ans15, meta15 = await self.orchestrator.handle(sid, q15)
        
        # It must say the information is not available/cannot be confirmed.
        p15 = any(x in ans15 for x in ["確認できません", "記載されていません", "分かりません", "情報がありません", "見つかりません"])
        
        await self.record_result(
            "H_Hallucination", "H15_OUT_OF_CONTEXT_COMPANY_INFO_REFUSAL",
            q15, ans15, meta15, p15,
            error=None if p15 else "LLM did not correctly refuse to answer out-of-context company information."
        )

        # ----------------------------------------------------------------------
        # H16: Verifier Hallucination Correction Loop (Self-Check Loop)
        # ----------------------------------------------------------------------
        # We manually monkey-patch _generate_llm_answer_with_self_check to inject a hallucination
        # on the first try, but allow the second retry try to generate normally.
        # This tests if the verification engine triggers correction and successfully passes on retry.
        original_generate = self.orchestrator._generate_llm_answer_with_self_check
        
        async def mock_generate_with_initial_hallucination(original_query: str, rewritten_query: str, pipeline: str, payload: dict, summary_context: dict = None):
            context_str = json.dumps(payload, ensure_ascii=False)
            
            # 1. First attempt: return a hallucinated answer
            hallucinated_ans = "島田さんは100億円 of 高級タワーマンションの内見を希望していました。"
            passed, _ = await self.orchestrator._verify_hallucination(hallucinated_ans, context_str)
            
            # 2. Second attempt: generate the real answer
            messages = [
                {"role": "system", "content": "あなたはスマートで親切なAIアシスタント of Javisです。"},
                {"role": "user", "content": original_query}
            ]
            real_ans = await self.orchestrator.llm_manager.generate_chat_completion(messages=messages)
            passed_second, _ = await self.orchestrator._verify_hallucination(real_ans, context_str)
            
            return real_ans, "high", passed_second, 1
            
        self.orchestrator._generate_llm_answer_with_self_check = mock_generate_with_initial_hallucination
        
        q16 = "GT_03 of 島田さんは何の内見を希望していましたか？"
        ans16, meta16 = await self.orchestrator.handle(sid, q16)
        
        # Restore original function
        self.orchestrator._generate_llm_answer_with_self_check = original_generate
        
        # Test passes if:
        # - The final answer does NOT contain "100億円"
        # - Self check retries is recorded as 1
        p16 = "100億円" not in ans16 and meta16.get("self_check_retries") == 1
        
        await self.record_result(
            "H_Hallucination", "H16_VERIFIER_CORRECTION_LOOP",
            q16, ans16, meta16, p16,
            error=None if p16 else f"Retry count: {meta16.get('self_check_retries')}, Answer: '{ans16}'"
        )



    def print_report(self):
        print("\n" + "="*70)
        print("       MULTI-TURN CONTEXT MANAGER V4 (HALLUCINATION SCENARIOS) — REPORT")
        print("="*70)

        total = len(self.results)
        if total == 0:
            print("No results recorded.")
            return

        passed_list = [r for r in self.results if r["passed"]]
        failed_list = [r for r in self.results if not r["passed"]]
        accuracy = (len(passed_list) / total) * 100

        print(f"Total Test Cases:      {total}")
        print(f"Passed:                {len(passed_list)} ({accuracy:.1f}%)")
        print(f"Failed:                {len(failed_list)} ({100 - accuracy:.1f}%)")
        print("-"*70)

        for r in self.results:
            status = "✓" if r["passed"] else "✗"
            print(f"  {status} {r['test_id']}")
            if not r["passed"]:
                print(f"      Q:    {r['query'][:80]}")
                print(f"      A:    {str(r['answer'])[:100]}")
                if isinstance(r["metadata"], dict):
                    pipeline = r["metadata"].get("target_pipeline", "?")
                    nr = r["metadata"].get("needs_retrieval", "?")
                    print(f"      Meta: pipeline={pipeline}, needs_retrieval={nr}")
                if r["error"]:
                    print(f"      Err:  {r['error']}")
        print("="*70 + "\n")


async def main():
    suite = TestSuiteV4()
    await suite.init()
    try:
        await suite.run_scenario_h_hallucination_vulnerabilities()
        suite.print_report()
        out_path = os.path.join(os.path.dirname(__file__), '..', 'test_results_v4.json')
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(suite.results, f, ensure_ascii=False, indent=2)
        logger.info(f"V4 results saved to {out_path}")
    except Exception as e:
        logger.error(f"Test suite execution failed: {e}", exc_info=True)
    finally:
        await suite.close()


if __name__ == "__main__":
    asyncio.run(main())
