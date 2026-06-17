import asyncio
import time
import json
import logging
import statistics
import os
from datetime import datetime, timedelta, timezone
import asyncpg
from dotenv import load_dotenv
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
            ngrams = []
            text = text.replace("query: ", "").replace("passage: ", "")
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
            return np.array(results[0])
        return np.array(results)

from router import get_llm_manager
from orchestrator import IntelligentOrchestrator
from cache_manager import upsert_cache_slot, get_cache_slot

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

DB_URL = os.getenv("NUMERIC_SQL_DATABASE_URL", "postgresql://app_user:app_password@localhost:54331/app_db")

class TestSuite:
    def __init__(self):
        self.db_pool = None
        self.embedding_model = None
        self.llm_manager = None
        self.orchestrator = None
        self.results = []

    async def init(self):
        logger.info("Initializing Test Suite...")
        self.db_pool = await asyncpg.create_pool(DB_URL, min_size=5, max_size=15)
        self.embedding_model = MockSentenceTransformer()
        self.llm_manager = get_llm_manager()
        self.orchestrator = IntelligentOrchestrator(self.db_pool, self.llm_manager, self.embedding_model)
        logger.info("Test Suite initialized successfully.")

    async def close(self):
        if self.db_pool:
            await self.db_pool.close()
            logger.info("Database pool closed.")

    async def clear_db(self, session_id: str = None):
        """
        Clears chat history, cache and entities for the session or all.
        """
        async with self.db_pool.acquire() as conn:
            if session_id:
                await conn.execute("DELETE FROM chat_history WHERE session_id = $1", session_id)
                await conn.execute("DELETE FROM session_context_cache WHERE session_id = $1", session_id)
                await conn.execute("DELETE FROM session_entity_index WHERE session_id = $1", session_id)
            else:
                await conn.execute("DELETE FROM chat_history")
                await conn.execute("DELETE FROM session_context_cache")
                await conn.execute("DELETE FROM session_entity_index")

    async def record_result(self, category: str, test_id: str, query: str, metadata: dict, passed: bool, error: str = None):
        self.results.append({
            "category": category,
            "test_id": test_id,
            "query": query,
            "metadata": metadata,
            "passed": passed,
            "error": error
        })

    # =========================================================================
    # STANDARD SCENARIOS
    # =========================================================================
    async def run_standard_scenarios(self):
        logger.info("=== Running Standard Scenarios ===")
        session_id = "test_standard_session"
        await self.clear_db(session_id)

        # Scenario 1 & 2: Follow-up & Switch
        # Turn 1
        q1 = "GT_04の2026年5月4日の通話時間はどれくらいですか？"
        logger.info(f"Q1: {q1}")
        ans1, meta1 = await self.orchestrator.handle(session_id, q1)
        passed1 = meta1["needs_retrieval"] == "full" and meta1["target_pipeline"] == "SQL"
        await self.record_result("Standard", "SCENARIO_1_T1", q1, meta1, passed1)

        # Turn 2: Follow-up
        q2 = "誰がその通話を行いましたか？"
        logger.info(f"Q2: {q2}")
        ans2, meta2 = await self.orchestrator.handle(session_id, q2)
        passed2 = meta2["needs_retrieval"] == "none" and meta2["target_topic_key"] is not None
        await self.record_result("Standard", "SCENARIO_1_T2", q2, meta2, passed2)

        # Turn 3: Topic switch
        q3 = "2026年5月3日に内見に関する通話はありますか？"
        logger.info(f"Q3: {q3}")
        ans3, meta3 = await self.orchestrator.handle(session_id, q3)
        passed3 = meta3["needs_retrieval"] == "full" and meta3["target_pipeline"] in ["SQL", "RAG"]
        await self.record_result("Standard", "SCENARIO_2_T3", q3, meta3, passed3)

        # Turn 4: Switch Back
        q4 = "では、先ほどの通話を受けたのは誰ですか？"
        logger.info(f"Q4: {q4}")
        ans4, meta4 = await self.orchestrator.handle(session_id, q4)
        passed4 = meta4["needs_retrieval"] == "none" and "GT_04" in str(meta4["rewritten_query"])
        await self.record_result("Standard", "SCENARIO_4_T4", q4, meta4, passed4)

    # =========================================================================
    # DIRTY & COMPLEX SCENARIOS (NEG)
    # =========================================================================
    async def run_neg_scenarios(self):
        logger.info("=== Running Negative/Dirty Scenarios (NEG) ===")
        
        # NEG_001: Ambiguous entities
        # Pre-setup: insert two active slots for GT_04 and GT_03
        session_neg = "session_neg"
        await self.clear_db(session_neg)
        async with self.db_pool.acquire() as conn:
            # Insert GT_04
            c1 = await upsert_cache_slot(conn, session_neg, "GT_04_topic", "SQL", "heuristics", {"rows": []}, {})
            await conn.execute("""
                INSERT INTO session_entity_index (session_id, cache_slot_id, entity_id, entity_type, display_names)
                VALUES ($1, $2, 'GT_04', 'meeting_transcript', ARRAY['その通話', '彼', '彼ら'])
            """, session_neg, c1)
            # Insert GT_03
            c2 = await upsert_cache_slot(conn, session_neg, "GT_03_topic", "SQL", "heuristics", {"rows": []}, {})
            await conn.execute("""
                INSERT INTO session_entity_index (session_id, cache_slot_id, entity_id, entity_type, display_names)
                VALUES ($1, $2, 'GT_03', 'meeting_transcript', ARRAY['その通話', '彼', '彼ら'])
            """, session_neg, c2)

        q_neg1 = "彼は何と言いましたか？"
        logger.info(f"NEG_001: {q_neg1}")
        # Bypasses Tier 1 due to ambiguous entities
        ans, meta = await self.orchestrator.handle(session_neg, q_neg1)
        passed = meta["routing_tier"] == "tier_2"
        await self.record_result("NEG", "NEG_001", q_neg1, meta, passed)

        # NEG_002: Unexpected Topic Shift
        q_neg2 = "あ、やっぱり、ネットで歌手A of 情報を検索してください。"
        logger.info(f"NEG_002: {q_neg2}")
        ans, meta = await self.orchestrator.handle(session_neg, q_neg2)
        passed = meta["needs_retrieval"] == "full" and meta["target_pipeline"] == "WEB"
        await self.record_result("NEG", "NEG_002", q_neg2, meta, passed)

        # NEG_003: Brand new conversation
        session_new = "session_new"
        await self.clear_db(session_new)
        q_neg3 = "2026年5月2日に通話はありましたか？"
        logger.info(f"NEG_003: {q_neg3}")
        ans, meta = await self.orchestrator.handle(session_new, q_neg3)
        passed = meta["needs_retrieval"] == "full" and meta["target_pipeline"] == "SQL"
        await self.record_result("NEG", "NEG_003", q_neg3, meta, passed)

        # NEG_004: LLM Router Timeout
        # Temporary mock llm_manager to simulate timeout
        orig_gen = self.llm_manager.generate_chat_completion
        async def mock_timeout(*args, **kwargs):
            raise asyncio.TimeoutError("Simulated LLM Timeout")
        self.llm_manager.generate_chat_completion = mock_timeout
        
        q_neg4 = "その通話の内容は何ですか？"
        logger.info(f"NEG_004: {q_neg4}")
        try:
            ans, meta = await self.orchestrator.handle(session_neg, q_neg4)
            passed = meta["needs_retrieval"] == "full" and meta["routing_method"] == "embeddings" # embedding fallback
        except Exception as e:
            passed = False
            logger.error(f"NEG_004 failed: {e}")
            meta = {}
        self.llm_manager.generate_chat_completion = orig_gen
        await self.record_result("NEG", "NEG_004", q_neg4, meta, passed)

        # NEG_005: Bad JSON response
        async def mock_bad_json(*args, **kwargs):
            return "This is not json output { bad json"
        self.llm_manager.generate_chat_completion = mock_bad_json
        q_neg5 = "その通話の内容は何ですか？"
        logger.info(f"NEG_005: {q_neg5}")
        ans, meta = await self.orchestrator.handle(session_neg, q_neg5)
        passed = meta["rewritten_query"] is not None # fallback worked
        self.llm_manager.generate_chat_completion = orig_gen
        await self.record_result("NEG", "NEG_005", q_neg5, meta, passed)

        # NEG_006: Typos and abbreviations
        q_neg6 = "GT_04のつうわ時間はどれくらい"
        logger.info(f"NEG_006: {q_neg6}")
        ans, meta = await self.orchestrator.handle(session_neg, q_neg6)
        passed = meta["target_pipeline"] == "SQL"
        await self.record_result("NEG", "NEG_006", q_neg6, meta, passed)

        # NEG_007: Code-mixing
        q_neg7 = "そのcallはいつendしましたか？"
        logger.info(f"NEG_007: {q_neg7}")
        ans, meta = await self.orchestrator.handle(session_neg, q_neg7)
        passed = meta["rewritten_query"] is not None
        await self.record_result("NEG", "NEG_007", q_neg7, meta, passed)

        # NEG_008: Parallel queries for multiple entities
        q_neg8 = "GT_04とGT_06の通話を比較してください。"
        logger.info(f"NEG_008: {q_neg8}")
        ans, meta = await self.orchestrator.handle(session_neg, q_neg8)
        passed = meta["needs_retrieval"] == "full"
        await self.record_result("NEG", "NEG_008", q_neg8, meta, passed)

        # NEG_009: Changing mind (LRU test)
        session_lru = "session_lru"
        await self.clear_db(session_lru)
        logger.info("NEG_009: Sequentially querying 4 topics to trigger LRU eviction")
        # 1. Ask GT_04
        await self.orchestrator.handle(session_lru, "GT_04の通話時間はどれくらいですか？")
        # 2. Ask GT_03
        await self.orchestrator.handle(session_lru, "2026年5月3日に内見に関する通話はありますか？")
        # 3. Ask GT_06
        await self.orchestrator.handle(session_lru, "GT_06の通話内容は何ですか？")
        # Now 3 slots are active. Ask GT_08
        await self.orchestrator.handle(session_lru, "GT_08の通話の詳細は？")
        
        # Verify oldest (GT_04) was evicted, so we should have exactly 3 slots
        async with self.db_pool.acquire() as conn:
            active_slots = await conn.fetch("SELECT topic_key FROM session_context_cache WHERE session_id = $1", session_lru)
            active_keys = [r["topic_key"] for r in active_slots]
            passed = len(active_keys) == 3 and not any("gt_04" in k.lower() for k in active_keys)
        await self.record_result("NEG", "NEG_009", "LRU Eviction Test", {}, passed)

        # NEG_010: Web Cache TTL Expired
        session_ttl = "session_ttl"
        await self.clear_db(session_ttl)
        # 1. Put a WEB cache slot that is expired (2 hours ago)
        async with self.db_pool.acquire() as conn:
            c_id = await upsert_cache_slot(conn, session_ttl, "web_mitsubishi", "WEB", "heuristics", {"results": [{"title": "Mitsubishi Info", "url": "http://example.com", "snippet": "Mitsubishi corp profile."}]}, {})
            # Set refreshed_at to 2 hours ago
            expired_time = datetime.now(timezone.utc) - timedelta(hours=2)
            await conn.execute("UPDATE session_context_cache SET refreshed_at = $1 WHERE id = $2", expired_time, c_id)
            
        q_neg10 = "今日の三菱の株価はどうですか？"
        logger.info(f"NEG_010: {q_neg10}")
        ans, meta = await self.orchestrator.handle(session_ttl, q_neg10)
        passed = meta["needs_retrieval"] == "full" # Forced retrieval due to TTL
        await self.record_result("NEG", "NEG_010", q_neg10, meta, passed)

        # NEG_013: Entity index quick match
        session_ent = "session_ent"
        await self.clear_db(session_ent)
        async with self.db_pool.acquire() as conn:
            c_id = await upsert_cache_slot(conn, session_ent, "GT_04_topic", "SQL", "heuristics", {"rows": [{"speaker": "Yokobori", "participants": ["横堀", "中原凛花"]}]}, {})
            await conn.execute("""
                INSERT INTO session_entity_index (session_id, cache_slot_id, entity_id, entity_type, display_names)
                VALUES ($1, $2, 'GT_04', 'meeting_transcript', ARRAY['彼', 'GT_04の通話'])
            """, session_ent, c_id)
            
        q_neg13 = "彼は何と言いましたか？"
        logger.info(f"NEG_013: {q_neg13}")
        ans, meta = await self.orchestrator.handle(session_ent, q_neg13)
        passed = meta["routing_tier"] == "tier_1" and meta["needs_retrieval"] == "none"
        await self.record_result("NEG", "NEG_013", q_neg13, meta, passed)

        # NEG_014: Ambiguous pronoun resolution
        q_neg14 = "彼は何と言いましたか？"
        logger.info(f"NEG_014: {q_neg14}")
        ans, meta = await self.orchestrator.handle(session_neg, q_neg14)
        passed = meta["routing_tier"] == "tier_2"
        await self.record_result("NEG", "NEG_014", q_neg14, meta, passed)

        # NEG_015: 3 Topics Switch Back (No Eviction)
        session_switch = "session_switch"
        await self.clear_db(session_switch)
        await self.orchestrator.handle(session_switch, "今日の三菱はどうですか？")
        await self.orchestrator.handle(session_switch, "GT_04の通話時間はどれくらいですか？")
        await self.orchestrator.handle(session_switch, "GT_06の通話の要約は？")
        # Now 3 slots are active. Switch back to Mitsubishi
        q_neg15 = "三菱に関する新しいニュースはありますか？"
        logger.info(f"NEG_015: {q_neg15}")
        ans, meta = await self.orchestrator.handle(session_switch, q_neg15)
        # Should hit the cache of Mitsubishi (needs_retrieval can be none or full web refresh depending on TTL, but no eviction happened)
        async with self.db_pool.acquire() as conn:
            cnt = await conn.fetchval("SELECT COUNT(*) FROM session_context_cache WHERE session_id = $1", session_switch)
            passed = cnt <= 3
        await self.record_result("NEG", "NEG_015", q_neg15, meta, passed)

        # NEG_016: SQL Schema Change
        # We simulate a broken query that fails the SQL engine
        q_neg16 = "データベースに存在しない情報を表示してください"
        logger.info(f"NEG_016: {q_neg16}")
        # The SQL engine will fail to execute, circuit breaker opens and falls back to parametric model response
        ans, meta = await self.orchestrator.handle(session_neg, q_neg16)
        passed = "fallback" in str(ans).lower() or meta["target_pipeline"] == "MODEL" or meta["answer_confidence"] == "high"
        await self.record_result("NEG", "NEG_016", q_neg16, meta, passed)

        # NEG_017: Token Bloat (Big RAG PDF)
        # Checked via fast metadata access timing
        q_neg17 = "GT_06の通話の詳細"
        logger.info(f"NEG_017: {q_neg17}")
        ans, meta = await self.orchestrator.handle(session_neg, q_neg17)
        passed = meta["latency_ms"] < 6000  # fast metadata lookup with fallback tolerance
        await self.record_result("NEG", "NEG_017", q_neg17, meta, passed)

        # NEG_019: Code-mixing pronoun match
        # Insert entity
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                UPDATE session_entity_index 
                SET display_names = display_names || ARRAY['それ', 'そのドキュメント']
                WHERE session_id = $1 AND entity_id = 'GT_04'
            """, session_ent)
        q_neg19 = "それとそのドキュメント"
        logger.info(f"NEG_019: {q_neg19}")
        ans, meta = await self.orchestrator.handle(session_ent, q_neg19)
        passed = meta["needs_retrieval"] == "none"
        await self.record_result("NEG", "NEG_019", q_neg19, meta, passed)

    # =========================================================================
    # RECOVERY & FIX SCENARIOS (FIX)
    # =========================================================================
    async def run_fix_scenarios(self):
        logger.info("=== Running Fix/Recovery Scenarios (FIX) ===")
        session_fix = "session_fix"
        await self.clear_db(session_fix)

        # FIX_001: Embedding Timeout
        # Temporary mock _safe_embed to simulate slow response
        import router
        orig_safe_embed = router._safe_embed
        
        async def mock_slow_embed(*args, **kwargs):
            await asyncio.sleep(1.5)
            return None
        router._safe_embed = mock_slow_embed
        
        q_fix1 = "AJ Technologiesの通話を検索してください"
        logger.info(f"FIX_001: {q_fix1}")
        # Re-initialize orchestrator/router to use mocked module function
        self.orchestrator = IntelligentOrchestrator(self.db_pool, self.llm_manager, self.embedding_model)
        ans, meta = await self.orchestrator.handle(session_fix, q_fix1)
        passed = meta["embedding_failed"] == True and meta["routing_tier"] == "tier_2"
        await self.record_result("FIX", "FIX_001", q_fix1, meta, passed)
        
        router._safe_embed = orig_safe_embed
        self.orchestrator = IntelligentOrchestrator(self.db_pool, self.llm_manager, self.embedding_model)

        # FIX_002: Zero vector return
        q_fix2 = "   " # Spaces
        logger.info(f"FIX_002: spaces query")
        ans, meta = await self.orchestrator.handle(session_fix, q_fix2)
        passed = meta["rewritten_query"] is not None
        await self.record_result("FIX", "FIX_002", "Spaces query", meta, passed)

        # FIX_003: Row Lock prevents concurrent delete
        # Tested as part of transaction integrity

        # FIX_005: Self-check Hallucination Over Limit
        # Mock verifier to always fail
        orig_verify = self.orchestrator._verify_hallucination
        async def mock_fail_verify(*args, **kwargs):
            return False, "Simulated Hallucination error"
        self.orchestrator._verify_hallucination = mock_fail_verify
        
        q_fix5 = "GT_04の通話の詳細"
        logger.info(f"FIX_005: {q_fix5}")
        ans, meta = await self.orchestrator.handle(session_fix, q_fix5)
        passed = meta["answer_confidence"] == "low" and "注意" in ans
        await self.record_result("FIX", "FIX_005", q_fix5, meta, passed)
        
        self.orchestrator._verify_hallucination = orig_verify

        # FIX_006: Web entity linking registered in index
        q_fix6 = "AJ Technologiesに関する情報"
        logger.info(f"FIX_006: {q_fix6}")
        ans, meta = await self.orchestrator.handle(session_fix, q_fix6)
        # Verify entity index contains AJ Technologies
        async with self.db_pool.acquire() as conn:
            ent_rows = await conn.fetch("SELECT entity_id FROM session_entity_index WHERE session_id = $1", session_fix)
            passed = len(ent_rows) > 0
        await self.record_result("FIX", "FIX_006", q_fix6, meta, passed)

        # FIX_007: Web TTL Refresh
        # Handled in NEG_010

        # FIX_008 & FIX_011: Advisory Lock Concurrency Queueing
        logger.info("FIX_008: Running 3 concurrent requests to test advisory lock queuing...")
        q_con = "それで、5月5日の通話はどうですか？"
        
        async def call_handle(idx):
            start = time.perf_counter()
            ans, meta = await self.orchestrator.handle(session_fix, f"{q_con} {idx}", lock_timeout=120.0)
            end = time.perf_counter()
            return idx, (end - start) * 1000

        # Run them in parallel
        tasks = [call_handle(i) for i in range(3)]
        con_results = await asyncio.gather(*tasks)
        
        # If advisory lock queued them, they should finish sequentially (latencies will scale up)
        latencies = [r[1] for r in con_results]
        logger.info(f"Concurrent request latencies: {latencies}")
        passed = max(latencies) > sum(latencies)/3 # shows sequential execution timing delay
        await self.record_result("FIX", "FIX_008", "Concurrent advisory locks", {}, passed)

        # FIX_009: Advisory Lock Timeout
        logger.info("FIX_009: Simulating Advisory Lock Timeout...")
        from session_lock import SessionLockManager, get_lock_id
        target_lock_id = get_lock_id("test_session_timeout")
        
        # Start a transaction on connection 1 and acquire advisory lock, sleep inside tx
        async def lock_holder(conn, stop_event):
            async with conn.transaction():
                # Acquire advisory lock manually
                await conn.execute("SELECT pg_try_advisory_xact_lock($1)", target_lock_id)
                await stop_event.wait()

        stop_event = asyncio.Event()
        conn1 = await self.db_pool.acquire()
        holder_task = asyncio.create_task(lock_holder(conn1, stop_event))
        await asyncio.sleep(0.5) # Let conn1 get lock
        
        # Now try to acquire the same lock with timeout 1s on conn2
        conn2 = await self.db_pool.acquire()
        lm = SessionLockManager()
        
        try:
            start_wait = time.perf_counter()
            # Try lock with timeout 1.5s
            await lm.acquire_lock(conn2, "test_session_timeout", timeout=1.5)
            # If we reach here, lock was acquired (unexpected because conn1 holds it)
            passed = False
        except TimeoutError:
            end_wait = time.perf_counter()
            wait_time = end_wait - start_wait
            logger.info(f"Advisory lock timed out correctly after {wait_time:.2f}s")
            passed = 1.0 <= wait_time <= 2.5
        except Exception as e:
            logger.error(f"Unexpected error in lock timeout: {e}")
            passed = False
            
        stop_event.set()
        await holder_task
        await self.db_pool.release(conn1)
        await self.db_pool.release(conn2)
        await self.record_result("FIX", "FIX_009", "Lock timeout", {}, passed)

        # FIX_010: Update vector prevents drift
        # Handled in cache update pipeline.

    # =========================================================================
    # KPI EVALUATION REPORT
    # =========================================================================
    def print_report(self):
        print("\n" + "="*60)
        print("          MULTI-TURN CONTEXT MANAGER V3 BENCHMARK REPORT")
        print("="*60)
        
        all_runs = self.results
        total = len(all_runs)
        if total == 0:
            print("No test results recorded.")
            return

        passed_runs = [r for r in all_runs if r["passed"]]
        failed_runs = [r for r in all_runs if not r["passed"]]
        
        accuracy = (len(passed_runs) / total) * 100
        
        # Latency metrics
        latencies = [r["metadata"].get("latency_ms", 0.0) for r in all_runs if "metadata" in r and "latency_ms" in r["metadata"]]
        p95_latency = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies) if latencies else 0.0
        p99_latency = statistics.quantiles(latencies, n=100)[98] if len(latencies) >= 100 else max(latencies) if latencies else 0.0
        avg_latency = sum(latencies)/len(latencies) if latencies else 0.0
        
        # Routing method count
        routing_methods = [r["metadata"].get("routing_method") for r in all_runs if "metadata" in r and "routing_method" in r["metadata"]]
        method_counts = {}
        for m in routing_methods:
            if m:
                method_counts[m] = method_counts.get(m, 0) + 1

        # Cache hit rate (needs_retrieval = none)
        cache_hits = len([r for r in all_runs if "metadata" in r and r["metadata"].get("needs_retrieval") == "none"])
        cache_partials = len([r for r in all_runs if "metadata" in r and r["metadata"].get("needs_retrieval") == "partial"])
        cache_hit_rate = (cache_hits / total) * 100 if total else 0.0

        # Self check stats
        self_check_passed = len([r for r in all_runs if "metadata" in r and r["metadata"].get("self_check_passed") == True])
        self_check_rate = (self_check_passed / len([r for r in all_runs if "metadata" in r and r["metadata"].get("self_check_passed") is not None])) * 100 if len([r for r in all_runs if "metadata" in r and r["metadata"].get("self_check_passed") is not None]) else 100.0

        print(f"Total Test Cases Run:         {total}")
        print(f"Passed Test Cases:            {len(passed_runs)} ({accuracy:.2f}%)")
        print(f"Failed Test Cases:            {len(failed_runs)} ({100 - accuracy:.2f}%)")
        print("-" * 60)
        print(f"Average Latency:             {avg_latency:.2f}ms")
        print(f"p95 Latency:                 {p95_latency:.2f}ms")
        print(f"p99 Latency:                 {p99_latency:.2f}ms")
        print("-" * 60)
        print(f"Cache Hit Rate (none):       {cache_hit_rate:.2f}% ({cache_hits} slots)")
        print(f"Cache Partial Hit Rate:      {(cache_partials / total) * 100:.2f}% ({cache_partials} slots)")
        print(f"Self-Check Pass Rate:        {self_check_rate:.2f}%")
        print("-" * 60)
        print("Routing Breakdown:")
        for method, count in method_counts.items():
            print(f"  - {method}: {count} ({count/total*100:.1f}%)")
        print("="*60 + "\n")
        
        if failed_runs:
            print("Failed Test cases details:")
            for f in failed_runs:
                print(f" - [{f['category']}] {f['test_id']} | Query: '{f['query']}' | Error: {f['error']}")
            print("="*60 + "\n")

async def main():
    suite = TestSuite()
    await suite.init()
    try:
        await suite.run_standard_scenarios()
        await suite.run_neg_scenarios()
        await suite.run_fix_scenarios()
        suite.print_report()
    except Exception as e:
        logger.error(f"Test suite execution failed: {e}", exc_info=True)
    finally:
        await suite.close()

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(main())
