import asyncio
import time
import json
import logging
import statistics
import os
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

# Mocking Sentence Transformer for fast testing
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

# Add 'src' directory to sys.path so we can import core modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from router import get_llm_manager
from orchestrator import IntelligentOrchestrator
from cache_manager import upsert_cache_slot, get_cache_slot

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

DB_URL = os.getenv("NUMERIC_SQL_DATABASE_URL", "postgresql://app_user:app_password@localhost:54331/app_db")

class TestSuiteV2:
    def __init__(self):
        self.db_pool = None
        self.embedding_model = None
        self.llm_manager = None
        self.orchestrator = None
        self.results = []

    async def init(self):
        logger.info("Initializing Test Suite V2...")
        self.db_pool = await asyncpg.create_pool(DB_URL, min_size=10, max_size=30)
        self.embedding_model = MockSentenceTransformer()
        self.llm_manager = get_llm_manager()
        self.orchestrator = IntelligentOrchestrator(self.db_pool, self.llm_manager, self.embedding_model)
        logger.info("Test Suite V2 initialized successfully.")

    async def close(self):
        if self.db_pool:
            await self.db_pool.close()
            logger.info("Database pool closed.")

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

    async def record_result(self, category: str, test_id: str, query: str, answer: str, metadata: dict, passed: bool, error: str = None):
        self.results.append({
            "category": category,
            "test_id": test_id,
            "query": query,
            "answer": answer,
            "metadata": metadata,
            "passed": passed,
            "error": error
        })

    # =========================================================================
    # STANDARD SCENARIOS (REAL-WORLD MULTI-TURN)
    # =========================================================================
    async def run_standard_scenarios(self):
        logger.info("=== Running Standard Multi-turn Scenarios ===")
        session_id = "v2_standard_session"
        await self.clear_db(session_id)

        # Turn 1: Initial Query on GT_04
        q1 = "GT_04の三菱UFJ銀行の横堀さんは誰に伝言を残しましたか？"
        ans1, meta1 = await self.orchestrator.handle(session_id, q1)
        passed1 = meta1["needs_retrieval"] == "full" and any(x in ans1 for x in ["中原", "凛花", "なかはら", "りんか"])
        await self.record_result("Standard", "STD_TURN_1", q1, ans1, meta1, passed1)

        # Turn 2: Follow-up pronoun reference (Nakahara Rinka)
        q2 = "彼女は当日出勤していましたか？"
        ans2, meta2 = await self.orchestrator.handle(session_id, q2)
        passed2 = meta2["needs_retrieval"] == "none" and any(x in ans2 for x in ["休み", "出勤していない", "いない"])
        await self.record_result("Standard", "STD_TURN_2_FOLLOWUP", q2, ans2, meta2, passed2)

        # Turn 3: Topic switch to GT_02
        q3 = "バルテスの中岡さんからの電話(GT_02)で、誰宛ての連絡でしたか？"
        ans3, meta3 = await self.orchestrator.handle(session_id, q3)
        passed3 = meta3["needs_retrieval"] == "full" and any(x in ans3 for x in ["石田", "志保", "いしだ", "しほ"])
        await self.record_result("Standard", "STD_TURN_3_SWITCH", q3, ans3, meta3, passed3)

        # Turn 4: Switch Back to GT_04 representative
        q4 = "では、先ほどの三菱UFJ銀行の担当者の名前は何でしたか？"
        ans4, meta4 = await self.orchestrator.handle(session_id, q4)
        passed4 = meta4["needs_retrieval"] == "none" and "横堀" in ans4
        await self.record_result("Standard", "STD_TURN_4_SWITCHBACK", q4, ans4, meta4, passed4)

    # =========================================================================
    # ADVANCED REASONING SCENARIOS
    # =========================================================================
    async def run_advanced_reasoning(self):
        logger.info("=== Running Advanced Reasoning Scenarios ===")
        session_id = "v2_reasoning_session"
        await self.clear_db(session_id)

        # Deep inquiry about GT_03
        q1 = "GT_03で島田さんは物件の何をしたかったと言っていましたか？"
        ans1, meta1 = await self.orchestrator.handle(session_id, q1)
        passed1 = meta1["target_pipeline"] == "RAG" and any(x in ans1 for x in ["内見", "物件", "見たい"])
        await self.record_result("Advanced", "RAG_DEEP_INQUIRY", q1, ans1, meta1, passed1)

        # Follow-up State Query
        q2 = "その物件は今どうなっていますか？"
        ans2, meta2 = await self.orchestrator.handle(session_id, q2)
        passed2 = meta1["target_topic_key"] == meta2["target_topic_key"] or "GT_03" in str(meta2.get("rewritten_query", ""))
        await self.record_result("Advanced", "FOLLOW_UP_STATE", q2, ans2, meta2, passed2)

        # Cross-document reasoning (GT_06, GT_07, GT_08 are all AJ Technologies)
        q3 = "GT_06, GT_07, GT_08の通話は、すべて何という会社からの連絡ですか？共通の会社名を答えてください。"
        ans3, meta3 = await self.orchestrator.handle(session_id, q3)
        passed3 = "AJ" in ans3 or "テクノロジーズ" in ans3
        await self.record_result("Advanced", "CROSS_DOC_REASONING", q3, ans3, meta3, passed3)

    # =========================================================================
    # SQL AGGREGATION SCENARIOS
    # =========================================================================
    async def run_sql_aggregation(self):
        logger.info("=== Running SQL Aggregation Scenarios ===")
        session_id = "v2_sql_session"
        await self.clear_db(session_id)

        q1 = "2026年5月1日から2026年5月9日までの通話の合計時間は？"
        ans1, meta1 = await self.orchestrator.handle(session_id, q1)
        passed1 = meta1["target_pipeline"] == "SQL" and ("秒" in ans1 or "分" in ans1)
        await self.record_result("SQL", "SUM_DURATION", q1, ans1, meta1, passed1)

        q2 = "その期間で、一番通話時間が長いのはどれですか？"
        ans2, meta2 = await self.orchestrator.handle(session_id, q2)
        passed2 = meta2["target_pipeline"] == "SQL" or "GT" in ans2
        await self.record_result("SQL", "MAX_DURATION", q2, ans2, meta2, passed2)

    # =========================================================================
    # ENTITY MEMORY SCENARIOS
    # =========================================================================
    async def run_entity_memory(self):
        logger.info("=== Running Entity Memory Scenarios ===")
        session_id = "v2_entity_session"
        await self.clear_db(session_id)

        await self.orchestrator.handle(session_id, "中原さん(Nakahara)について教えて。")
        await self.orchestrator.handle(session_id, "島田さん(Shimada)は？")
        
        q3 = "彼らは同じ目的で電話しましたか？"
        ans3, meta3 = await self.orchestrator.handle(session_id, q3)
        passed3 = any(x in ans3 for x in ["いいえ", "異なり", "違う", "別", "ない"])
        await self.record_result("Entity", "ENTITY_COMPARISON", q3, ans3, meta3, passed3)

    # =========================================================================
    # NEGATIVE / DIRTY SCENARIOS (NEG)
    # =========================================================================
    async def run_neg_scenarios(self):
        logger.info("=== Running Negative/Dirty Scenarios (NEG) ===")
        session_neg = "v2_session_neg"
        await self.clear_db(session_neg)

        # NEG_001: Ambiguous entities (Insert two similar pronouns/entities in cache)
        async with self.db_pool.acquire() as conn:
            c1 = await upsert_cache_slot(conn, session_neg, "GT_04_topic", "SQL", "heuristics", {"rows": []}, {})
            await conn.execute("""
                INSERT INTO session_entity_index (session_id, cache_slot_id, entity_id, entity_type, display_names)
                VALUES ($1, $2, 'GT_04', 'meeting_transcript', ARRAY['その通話', '彼', '彼ら'])
            """, session_neg, c1)
            c2 = await upsert_cache_slot(conn, session_neg, "GT_03_topic", "SQL", "heuristics", {"rows": []}, {})
            await conn.execute("""
                INSERT INTO session_entity_index (session_id, cache_slot_id, entity_id, entity_type, display_names)
                VALUES ($1, $2, 'GT_03', 'meeting_transcript', ARRAY['その通話', '彼', '彼ら'])
            """, session_neg, c2)

        q_neg1 = "彼は何と言いましたか？"
        ans, meta = await self.orchestrator.handle(session_neg, q_neg1)
        passed1 = meta["routing_tier"] == "tier_2"
        await self.record_result("NEG", "NEG_001_AMBIGUOUS_ENTITY", q_neg1, ans, meta, passed1)

        # NEG_002: Unexpected Topic Shift
        q_neg2 = "あ、やっぱり、ネットで歌手A of 情報を検索してください。"
        ans, meta = await self.orchestrator.handle(session_neg, q_neg2)
        passed2 = meta["needs_retrieval"] == "full" and meta["target_pipeline"] == "WEB"
        await self.record_result("NEG", "NEG_002_TOPIC_SHIFT", q_neg2, ans, meta, passed2)

        # NEG_006: Typos and abbreviations
        q_neg6 = "GT_04のつうわ時間はどれくらい"
        ans, meta = await self.orchestrator.handle(session_neg, q_neg6)
        passed6 = meta["target_pipeline"] == "SQL"
        await self.record_result("NEG", "NEG_006_TYPOS", q_neg6, ans, meta, passed6)

        # NEG_007: Code-mixing
        q_neg7 = "そのcallはいつendしましたか？"
        ans, meta = await self.orchestrator.handle(session_neg, q_neg7)
        passed7 = meta["rewritten_query"] is not None
        await self.record_result("NEG", "NEG_007_CODE_MIXING", q_neg7, ans, meta, passed7)

        # NEG_009: LRU Eviction verification
        session_lru = "v2_session_lru"
        await self.clear_db(session_lru)
        await self.orchestrator.handle(session_lru, "GT_04の通話時間はどれくらいですか？")
        await self.orchestrator.handle(session_lru, "今日の東京の天気はどうですか？")
        await self.orchestrator.handle(session_lru, "三菱の最近の株価は？")
        await self.orchestrator.handle(session_lru, "GT_08の通話の詳細は何ですか？")
        await self.orchestrator.handle(session_lru, "GT_03で島田さんは何を希望していましたか？")
        await self.orchestrator.handle(session_lru, "GT_09の伊藤さんはどこの会社ですか？") # 6th unique topic -> triggers LRU
        
        async with self.db_pool.acquire() as conn:
            active_slots = await conn.fetch("SELECT topic_key FROM session_context_cache WHERE session_id = $1", session_lru)
            active_keys = [r["topic_key"] for r in active_slots]
            passed9 = len(active_keys) == 5 and not any("gt_04" in k.lower() for k in active_keys)
        await self.record_result("NEG", "NEG_009_LRU_EVICTION", "LRU check", "Checked DB slots", {}, passed9)

        # NEG_010: Web Cache TTL Expired
        session_ttl = "v2_session_ttl"
        await self.clear_db(session_ttl)
        async with self.db_pool.acquire() as conn:
            c_id = await upsert_cache_slot(conn, session_ttl, "web_mitsubishi", "WEB", "heuristics", {"results": [{"title": "Mitsubishi Corp", "url": "http://example.com", "snippet": "Old info."}]}, {})
            expired_time = datetime.now(timezone.utc) - timedelta(hours=2)
            await conn.execute("UPDATE session_context_cache SET refreshed_at = $1 WHERE id = $2", expired_time, c_id)
            
        q_neg10 = "今日の三菱の株価はどうですか？"
        ans, meta = await self.orchestrator.handle(session_ttl, q_neg10)
        passed10 = meta["needs_retrieval"] == "full"
        await self.record_result("NEG", "NEG_010_TTL_EXPIRED", q_neg10, ans, meta, passed10)

        # NEG_016: SQL Schema Change fallback check
        q_neg16 = "データベースに存在しないテーブル情報を表示してください"
        ans, meta = await self.orchestrator.handle(session_neg, q_neg16)
        passed16 = meta["target_pipeline"] in ["MODEL", "SQL"]
        await self.record_result("NEG", "NEG_016_SQL_FAILURE_FALLBACK", q_neg16, ans, meta, passed16)

    # =========================================================================
    # RECOVERY / SYSTEM FIX SCENARIOS (FIX)
    # =========================================================================
    async def run_fix_scenarios(self):
        logger.info("=== Running Fix/Recovery Scenarios (FIX) ===")
        session_fix = "v2_session_fix"
        await self.clear_db(session_fix)

        # FIX_001: Embedding Timeout Recovery
        import router
        orig_safe_embed = router._safe_embed
        async def mock_slow_embed(*args, **kwargs):
            await asyncio.sleep(1.2)
            return None
        router._safe_embed = mock_slow_embed
        
        q_fix1 = "AJ Technologiesの通話を検索してください"
        self.orchestrator = IntelligentOrchestrator(self.db_pool, self.llm_manager, self.embedding_model)
        ans, meta = await self.orchestrator.handle(session_fix, q_fix1)
        passed1 = meta["embedding_failed"] == True and meta["routing_tier"] == "tier_2"
        await self.record_result("FIX", "FIX_001_EMBEDDING_TIMEOUT", q_fix1, ans, meta, passed1)
        
        router._safe_embed = orig_safe_embed
        self.orchestrator = IntelligentOrchestrator(self.db_pool, self.llm_manager, self.embedding_model)

        # FIX_005: Hallucination self-check retry limit hit
        orig_verify = self.orchestrator._verify_hallucination
        async def mock_fail_verify(*args, **kwargs):
            return False, "Simulated Hallucination"
        self.orchestrator._verify_hallucination = mock_fail_verify
        
        q_fix5 = "GT_04の通話の詳細"
        ans, meta = await self.orchestrator.handle(session_fix, q_fix5)
        passed5 = meta["answer_confidence"] == "low" and "注意" in ans
        await self.record_result("FIX", "FIX_005_HALLUCINATION_LIMIT", q_fix5, ans, meta, passed5)
        
        self.orchestrator._verify_hallucination = orig_verify

        # FIX_008: Advisory Lock Concurrency Queueing
        logger.info("FIX_008: Running concurrent requests on session_fix...")
        q_con = "それで、5月5日の通話はどうですか？"
        async def call_handle(idx):
            start = time.perf_counter()
            ans, meta = await self.orchestrator.handle(session_fix, f"{q_con} {idx}", lock_timeout=120.0)
            end = time.perf_counter()
            return idx, (end - start) * 1000
            
        tasks = [call_handle(i) for i in range(3)]
        con_results = await asyncio.gather(*tasks)
        latencies = [r[1] for r in con_results]
        passed8 = max(latencies) > sum(latencies)/3
        await self.record_result("FIX", "FIX_008_LOCK_CONCURRENCY", "Concurrent calls", "Sequential completion check", {}, passed8)

        # FIX_009: Advisory Lock Timeout
        logger.info("FIX_009: Simulating Advisory Lock Timeout...")
        from session_lock import SessionLockManager, get_lock_id
        target_lock_id = get_lock_id("v2_session_lock_timeout")
        
        async def lock_holder(conn, stop_event):
            async with conn.transaction():
                await conn.execute("SELECT pg_try_advisory_xact_lock($1)", target_lock_id)
                await stop_event.wait()

        stop_event = asyncio.Event()
        conn1 = await self.db_pool.acquire()
        holder_task = asyncio.create_task(lock_holder(conn1, stop_event))
        await asyncio.sleep(0.5) # Let conn1 acquire it
        
        conn2 = await self.db_pool.acquire()
        lm = SessionLockManager()
        try:
            start_wait = time.perf_counter()
            await lm.acquire_lock(conn2, "v2_session_lock_timeout", timeout=1.0)
            passed9 = False
        except TimeoutError:
            end_wait = time.perf_counter()
            wait_time = end_wait - start_wait
            logger.info(f"Lock timed out as expected after {wait_time:.2f}s")
            passed9 = 0.5 <= wait_time <= 2.0
        except Exception:
            passed9 = False
            
        stop_event.set()
        await holder_task
        await self.db_pool.release(conn1)
        await self.db_pool.release(conn2)
        await self.record_result("FIX", "FIX_009_LOCK_TIMEOUT", "Lock timeout simulation", "TimeoutError triggered", {}, passed9)

    # =========================================================================
    # STRESS TEST SCENARIOS
    # =========================================================================
    async def run_stress_test(self):
        logger.info("=== Running Stress/Concurrency Scenarios ===")
        session_id = "v2_stress_session"
        await self.clear_db(session_id)

        queries = [
            "GT_01からGT_09の通話内容を要約して比較してください。",
            "一番重要な通話はどれですか？その理由は？",
            "2026年5月の通話トレンドを分析してください。",
            "Asset Japanに関わる主要人物をリストアップしてください。",
            "未解決の件はありますか？"
        ]

        async def stress_worker(q, idx):
            start = time.perf_counter()
            ans, meta = await self.orchestrator.handle(session_id, q, lock_timeout=360.0)
            end = time.perf_counter()
            return idx, (end - start) * 1000, meta

        tasks = [stress_worker(q, i) for i, q in enumerate(queries)]
        results = await asyncio.gather(*tasks)
        latencies = [r[1] for r in results]
        all_passed = all(r[2].get("routing_tier") is not None for r in results)
        await self.record_result("Stress", "CONCURRENT_5_REQS", "Parallel queries", "Multiple Answers", {"avg_latency": sum(latencies)/5}, all_passed)

    # =========================================================================
    # BENCHMARK KPI REPORT
    # =========================================================================
    def print_report(self):
        print("\n" + "="*60)
        print("          MULTI-TURN CONTEXT MANAGER V2 - FINAL REPORT")
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
        
        for r in all_runs:
            status = "PASS" if r["passed"] else "FAIL"
            print(f"[{status}] {r['category']:<10} | {r['test_id']:<30}")
            if not r["passed"]:
                print(f"      Query:  {r['query']}")
                print(f"      Answer: {str(r['answer'])[:100]}...")
                print(f"      Meta:   {r['metadata']}")
                if r["error"]:
                    print(f"      Error:  {r['error']}")
        print("="*60 + "\n")

async def main():
    suite = TestSuiteV2()
    await suite.init()
    try:
        await suite.run_standard_scenarios()
        await suite.run_advanced_reasoning()
        await suite.run_sql_aggregation()
        await suite.run_entity_memory()
        await suite.run_neg_scenarios()
        await suite.run_fix_scenarios()
        await suite.run_stress_test()
        suite.print_report()
        
        # Save results for extraction
        with open("test_results_v2.json", "w", encoding="utf-8") as f:
            json.dump(suite.results, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        logger.error(f"Test suite execution failed: {e}", exc_info=True)
    finally:
        await suite.close()

if __name__ == "__main__":
    asyncio.run(main())
