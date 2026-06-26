import os
import sys

# Limit linear algebra threads to prevent Windows memory errors
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import asyncio
import time
import json
import logging
import re
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
        return np.array(results)


class TestSuiteV5:
    """
    Test Suite V5: Focuses on two major production-level aspects:
    1. Fuzzy Matching & Phonetic Noise (STT transcript errors, Romaji, Katakana, abbreviations).
    2. History Bloat & Cache Eviction (LRU limits, 50-turn conversation history pruning, recency checks).
    """
    def __init__(self):
        self.db_pool = None
        self.embedding_model = None
        self.llm_manager = None
        self.orchestrator = None
        self.results = []

    async def init(self):
        logger.info("Initializing Test Suite V5...")
        self.db_pool = await asyncpg.create_pool(DB_URL, min_size=10, max_size=30)
        self.embedding_model = MockSentenceTransformer()
        self.llm_manager = get_llm_manager()
        self.orchestrator = IntelligentOrchestrator(self.db_pool, self.llm_manager, self.embedding_model)
        logger.info("Test Suite V5 initialized.")

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

    async def record_result(self, category, test_id, query, answer, rewritten_query, routing_meta, passed, error=None):
        self.results.append({
            "category": category,
            "test_id": test_id,
            "query": query,
            "answer": answer,
            "rewritten_query": rewritten_query,
            "routing_meta": routing_meta,
            "passed": passed,
            "error": error
        })

    # ==========================================================================
    # SCENARIO F: FUZZY MATCHING & PHONETIC NOISE (STT / TYPOS)
    # ==========================================================================
    async def run_scenario_f_fuzzy_matching(self):
        logger.info("=== RUNNING SCENARIO F: Fuzzy Matching & Phonetic Noise ===")
        sid = "v5_fuzzy_tests"
        await self.clear_db(sid)

        # Seed initial Kanji-based entities in database
        async with self.db_pool.acquire() as conn:
            c_id = await upsert_cache_slot(
                conn, sid, "GT_11_topic", "RAG", "heuristics",
                {"documents": [{"chunk_id": "c11", "text": "佐藤太郎さんはアセットジャパンに所属する営業担当者です。"}]},
                {"entity_id": "GT_11", "entity_type": "meeting_transcript"}
            )
            # Add entity details
            await conn.execute("""
                INSERT INTO session_entity_index (session_id, cache_slot_id, entity_id, entity_type, display_names, attributes)
                VALUES ($1, $2, 'GT_11_佐藤太郎', 'person', ARRAY['佐藤太郎', '佐藤', '太郎'], '{"gender":"male", "company":"アセットジャパン"}')
            """, sid, c_id)
            await conn.execute("""
                INSERT INTO session_entity_index (session_id, cache_slot_id, entity_id, entity_type, display_names)
                VALUES ($1, $2, 'GT_11_company', 'document', ARRAY['アセットジャパン', 'アセット', 'AJ'])
            """, sid, c_id)

        # ----------------------------------------------------------------------
        # F1: Katakana Name Phonetic Matching
        # ----------------------------------------------------------------------
        q1 = "サトウさんはアセットジャパンの社員ですか？"
        ans1, meta1 = await self.orchestrator.handle(sid, q1)
        rewritten1 = meta1.get("rewritten_query", "")
        
        # Check if the router matched "サトウ" (Katakana) to "佐藤太郎" (Kanji) or resolved via Tier 2 successfully
        passed1 = "佐藤" in rewritten1 or "佐藤太郎" in rewritten1 or "佐藤" in ans1 or "太郎" in ans1
        await self.record_result(
            "F_Fuzzy_Matching", "F1_KATAKANA_NAME",
            q1, ans1, rewritten1, meta1, passed1,
            error=None if passed1 else "Katakana 'サトウ' was not mapped to Kanji '佐藤'"
        )

        # ----------------------------------------------------------------------
        # F2: Romaji/English Representation of Japanese Names
        # ----------------------------------------------------------------------
        q2 = "Sato Taroさんの会社の情報について教えてください。"
        ans2, meta2 = await self.orchestrator.handle(sid, q2)
        rewritten2 = meta2.get("rewritten_query", "")
        
        passed2 = "佐藤" in rewritten2 or "佐藤太郎" in rewritten2 or "佐藤" in ans2 or "太郎" in ans2
        await self.record_result(
            "F_Fuzzy_Matching", "F2_ROMAJI_NAME",
            q2, ans2, rewritten2, meta2, passed2,
            error=None if passed2 else "Romaji 'Sato Taro' was not mapped to Kanji '佐藤太郎'"
        )

        # ----------------------------------------------------------------------
        # F3: Company Initials & Abbreviations
        # ----------------------------------------------------------------------
        q3 = "AJの佐藤太郎さんはどのような立場ですか？"
        ans3, meta3 = await self.orchestrator.handle(sid, q3)
        rewritten3 = meta3.get("rewritten_query", "")
        
        passed3 = "アセット" in rewritten3 or "アセットジャパン" in rewritten3 or "アセットジャパン" in ans3
        await self.record_result(
            "F_Fuzzy_Matching", "F3_COMPANY_ABBREVIATION",
            q3, ans3, rewritten3, meta3, passed3,
            error=None if passed3 else "Abbreviation 'AJ' was not mapped to 'アセットジャパン'"
        )

        # ----------------------------------------------------------------------
        # F4: Speech-to-Text Transcription Typo (Voiced/Unvoiced Confusion)
        # ----------------------------------------------------------------------
        # Seed another participant "島田" (Shimada)
        async with self.db_pool.acquire() as conn:
            # Clean up first
            await conn.execute("DELETE FROM session_entity_index WHERE session_id = $1 AND entity_id = 'GT_03_島田'", sid)
            await conn.execute("""
                INSERT INTO session_entity_index (session_id, cache_slot_id, entity_id, entity_type, display_names)
                VALUES ($1, $2, 'GT_03_島田', 'person', ARRAY['島田', 'しまだ'])
            """, sid, c_id)
            
        q4 = "シマタさんは何の内見を希望していましたか？" # "シマタ" (Shimata) instead of "島田/しまだ" (Shimada)
        ans4, meta4 = await self.orchestrator.handle(sid, q4)
        rewritten4 = meta4.get("rewritten_query", "")
        
        passed4 = "島田" in rewritten4 or "島田" in ans4 or "内見" in ans4
        await self.record_result(
            "F_Fuzzy_Matching", "F4_STT_TYPO_CONFUSION",
            q4, ans4, rewritten4, meta4, passed4,
            error=None if passed4 else "Typo 'シマタ' was not resolved to '島田'"
        )

    # ==========================================================================
    # SCENARIO B: HISTORY BLOAT & CACHE EVICTION
    # ==========================================================================
    async def run_scenario_b_history_bloat(self):
        logger.info("=== RUNNING SCENARIO B: History Bloat & Cache Eviction ===")
        
        # ----------------------------------------------------------------------
        # B1: Cache LRU Eviction Under Max Slots Load
        # ----------------------------------------------------------------------
        sid_lru = "v5_lru_eviction_test"
        await self.clear_db(sid_lru)
        
        async with self.db_pool.acquire() as conn:
            # We seed 6 distinct slots. Since MAX_CACHE_SLOTS = 5, the first slot must be evicted.
            slot_ids = []
            for i in range(1, 7):
                topic = f"topic_{i}"
                c_id = await upsert_cache_slot(
                    conn, sid_lru, topic, "SQL", "heuristics",
                    {"rows": [{"id": i, "content": f"data_{i}"}]},
                    {"entity_id": f"entity_{i}", "entity_type": "meeting_transcript"}
                )
                slot_ids.append(c_id)
                # Sleep briefly to ensure timestamps differ
                await asyncio.sleep(0.05)
                
            # Count the remaining slots in the DB
            slots_count = await conn.fetchval(
                "SELECT COUNT(*) FROM session_context_cache WHERE session_id = $1", sid_lru
            )
            
            # Check if oldest slot (topic_1) was deleted
            oldest_exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM session_context_cache WHERE session_id = $1 AND topic_key = 'topic_1')", sid_lru
            )
            
        passed_b1 = (slots_count == 5) and (not oldest_exists)
        await self.record_result(
            "B_History_Bloat", "B1_LRU_CACHING_LIMIT",
            "Seed 6 slots sequentially", f"Cache size: {slots_count}, Oldest Exists: {oldest_exists}",
            "N/A", {}, passed_b1,
            error=None if passed_b1 else f"Slots count={slots_count} (expected 5), Oldest topic_1 exists={oldest_exists} (expected False)"
        )

        # ----------------------------------------------------------------------
        # B2: 50-Turn Conversation Pronoun Recency Check (Exposing History Limits)
        # ----------------------------------------------------------------------
        # In a real conversation, history grows. We will simulate 50 turns of conversation.
        # We start with GT_04 (Yokobori, male), then have 46 general turns of noise,
        # and finally GT_03 (Shimada, male) at Turn 48.
        # At Turn 50, we ask: "彼が気にした理由は何ですか？" (Why did he care?)
        # Since Shimada (GT_03) is the most recent male entity, it must resolve to Shimada.
        # But if the history fetching SQL uses ORDER BY id ASC LIMIT 16, it only sees the oldest 16 turns,
        # which means it will see Yokobori (GT_04) and completely miss Shimada (GT_03)!
        sid_bloat = "v5_history_bloat_test"
        await self.clear_db(sid_bloat)
        
        async with self.db_pool.acquire() as conn:
            # Seed Yokobori (GT_04) entity mappings
            c_yokobori = await upsert_cache_slot(
                conn, sid_bloat, "GT_04_topic", "RAG", "heuristics",
                {"documents": [{"chunk_id": "c_yokobori", "text": "横堀さんは中原凛花さんあて to 伝言を残しました。"}]},
                {"entity_id": "GT_04", "entity_type": "meeting_transcript"}
            )
            await conn.execute("""
                INSERT INTO session_entity_index (session_id, cache_slot_id, entity_id, entity_type, display_names, attributes)
                VALUES ($1, $2, 'GT_04_横堀', 'person', ARRAY['横堀', 'よこぼり'], '{"gender":"male"}')
            """, sid_bloat, c_yokobori)
            
            # Turn 1-2: User/Assistant about Yokobori (GT_04)
            await conn.execute("""
                INSERT INTO chat_history (session_id, role, content, rewritten_content)
                VALUES ($1, 'user', 'GT_04 of 横堀さんについて教えてください。', 'GT_04 of 横堀さんについて教えてください。')
            """, sid_bloat)
            await conn.execute("""
                INSERT INTO chat_history (session_id, role, content)
                VALUES ($1, 'assistant', '横堀さんは三菱UFJ銀行の人で、中原さんあてに伝言をお願いしていました。')
            """, sid_bloat)
            
            # Turn 3-44: General conversation noise (42 messages / 21 turns)
            for i in range(3, 45):
                role = 'user' if i % 2 == 1 else 'assistant'
                content = f"雑談やノイズの対話文 {i} です。"
                await conn.execute("""
                    INSERT INTO chat_history (session_id, role, content)
                    VALUES ($1, $2, $3)
                """, sid_bloat, role, content)
                
            # Seed Shimada (GT_03) entity mappings
            c_shimada = await upsert_cache_slot(
                conn, sid_bloat, "GT_03_topic", "RAG", "heuristics",
                {"documents": [{"chunk_id": "c_shimada", "text": "島田さんは物件の内見を希望しています。"}]},
                {"entity_id": "GT_03", "entity_type": "meeting_transcript"}
            )
            await conn.execute("""
                INSERT INTO session_entity_index (session_id, cache_slot_id, entity_id, entity_type, display_names, attributes)
                VALUES ($1, $2, 'GT_03_島田', 'person', ARRAY['島田', 'しまだ'], '{"gender":"male"}')
            """, sid_bloat, c_shimada)
            
            # Turn 45-48: Conversations about Shimada (GT_03)
            await conn.execute("""
                INSERT INTO chat_history (session_id, role, content, rewritten_content)
                VALUES ($1, 'user', 'GT_03 of 島田さんについて教えてください。', 'GT_03 of 島田さんについて教えてください。')
            """, sid_bloat)
            await conn.execute("""
                INSERT INTO chat_history (session_id, role, content)
                VALUES ($1, 'assistant', '島田さんはアセットジャパンの売り物件について内見を希望し、物件の前にいました。')
            """, sid_bloat)
            
            # Update cache timestamps to make Shimada the most recent hot cache slot
            await conn.execute("UPDATE session_context_cache SET last_accessed_at = NOW() WHERE id = $1", c_shimada)
            await conn.execute("UPDATE session_context_cache SET last_accessed_at = NOW() - INTERVAL '1 hour' WHERE id = $1", c_yokobori)

        q5 = "彼が気にした理由は何ですか？" # Turn 49: referring to Shimada (GT_03)
        ans5, meta5 = await self.orchestrator.handle(sid_bloat, q5)
        rewritten5 = meta5.get("rewritten_query", "")
        
        # Verify the pronoun resolved to Shimada (GT_03) rather than Yokobori (GT_04)
        resolved_to_shimada = "島田" in rewritten5 or "GT_03" in rewritten5
        resolved_to_yokobori = "横堀" in rewritten5 or "GT_04" in rewritten5
        
        passed5 = resolved_to_shimada and not resolved_to_yokobori
        
        err_msg = None
        if not passed5:
            if resolved_to_yokobori:
                err_msg = "LIMIT 16 History Order Bug: Resolved to the oldest male (Yokobori) instead of the newest (Shimada)."
            else:
                err_msg = f"Failed pronoun resolution. Rewritten query: '{rewritten5}'"
                
        await self.record_result(
            "B_History_Bloat", "B2_DEEP_HISTORY_RECENCY_CHECK",
            q5, ans5, rewritten5, meta5, passed5,
            error=err_msg
        )


    def print_report(self):
        print("\n" + "="*70)
        print("       MULTI-TURN CONTEXT MANAGER V5 (STRESS & FUZZY TESTS) — REPORT")
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
            print(f"      Category:  {r['category']}")
            print(f"      Q:         {r['query'][:80]}")
            print(f"      Rewrite:   {r['rewritten_query']}")
            if not r["passed"] and r["error"]:
                print(f"      Err:       {r['error']}")
        print("="*70 + "\n")


async def main():
    suite = TestSuiteV5()
    await suite.init()
    try:
        # Run tests
        await suite.run_scenario_f_fuzzy_matching()
        await suite.run_scenario_b_history_bloat()
        
        # Print report
        suite.print_report()
        
        # Save results
        out_path = os.path.join(os.path.dirname(__file__), '..', 'test_results_v5.json')
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(suite.results, f, ensure_ascii=False, indent=2)
        logger.info(f"V5 results saved to {out_path}")
    except Exception as e:
        logger.error(f"Test suite execution failed: {e}", exc_info=True)
    finally:
        await suite.close()


if __name__ == "__main__":
    asyncio.run(main())
