import os
import sys
import uuid

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
                await conn.execute("DELETE FROM chunks_turn WHERE transcript_id IN (SELECT id FROM transcripts WHERE session_id = 'GT_11')")
                await conn.execute("DELETE FROM transcripts WHERE session_id = 'GT_11'")

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
            # Clean up existing GT_11 to prevent duplicate keys
            await conn.execute("DELETE FROM chunks_turn WHERE transcript_id IN (SELECT id FROM transcripts WHERE session_id = 'GT_11')")
            await conn.execute("DELETE FROM transcripts WHERE session_id = 'GT_11'")
            
            # Seed main transcripts database with GT_11 for full retrieval integration
            t_id = uuid.uuid4()
            await conn.execute("""
                INSERT INTO transcripts (id, session_id, meeting_date, participants, speaker_count, duration_seconds, raw_text, summary)
                VALUES ($1, 'GT_11', '2026-06-26', '["佐藤太郎", "島田"]'::jsonb, 2, 120, 
                        '佐藤太郎: 私はアセットジャパンの佐藤太郎です。営業を担当しております。', 
                        '佐藤太郎さんはアセットジャパンの営業担当者です。')
            """, t_id)
            await conn.execute("""
                INSERT INTO chunks_turn (id, transcript_id, turn_index, speaker, time_start_sec, time_end_sec, text)
                VALUES ($1, $2, 0, '佐藤太郎', 0, 30, '私はアセットジャパンの佐藤太郎です。営業を担当しております。')
            """, uuid.uuid4(), t_id)

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
        
        # Check strictly that "島田" (Kanji) is resolved in rewritten_query or ans to prevent false positives from "内見"
        passed4 = "島田" in rewritten4 or "島田" in ans4
        await self.record_result(
            "F_Fuzzy_Matching", "F4_STT_TYPO_CONFUSION",
            q4, ans4, rewritten4, meta4, passed4,
            error=None if passed4 else "Typo 'シマタ' was not resolved to '島田'"
        )

        # ----------------------------------------------------------------------
        # F5: Phonetic Ambiguity (Resolving between two similar-sounding names)
        # ----------------------------------------------------------------------
        # Seed both "島田" (Shimada) and "島津" (Shimazu)
        async with self.db_pool.acquire() as conn:
            # Delete first
            await conn.execute("DELETE FROM session_entity_index WHERE session_id = $1 AND entity_id IN ('GT_12_島田', 'GT_12_島津')", sid)
            await conn.execute("""
                INSERT INTO session_entity_index (session_id, cache_slot_id, entity_id, entity_type, display_names, attributes)
                VALUES ($1, $2, 'GT_12_島田', 'person', ARRAY['島田', 'しまだ'], '{"gender":"female", "company":"アセットジャパン"}')
            """, sid, c_id)
            await conn.execute("""
                INSERT INTO session_entity_index (session_id, cache_slot_id, entity_id, entity_type, display_names, attributes)
                VALUES ($1, $2, 'GT_12_島津', 'person', ARRAY['島津', 'しまづ'], '{"gender":"male", "company":"アセットジャパン"}')
            """, sid, c_id)
            
        q5 = "シマタさんはどちらの会社の人ですか？" # "シマタ" is closer to "島田" (Shimada) than "島津" (Shimazu) due to voicing
        ans5, meta5 = await self.orchestrator.handle(sid, q5)
        rewritten5 = meta5.get("rewritten_query", "")
        
        # Verify it mapped "シマタ" to "島田" (Shimada), not "島津" (Shimazu)
        passed5 = "島田" in rewritten5 or "島田" in ans5
        failed_by_shimazu = "島津" in rewritten5 or "島津" in ans5
        passed5 = passed5 and not failed_by_shimazu
        
        await self.record_result(
            "F_Fuzzy_Matching", "F5_PHONETIC_AMBIGUITY",
            q5, ans5, rewritten5, meta5, passed5,
            error=None if passed5 else f"Fuzzy matching resolved to '島津' or failed to resolve to '島田'. Rewrite: {rewritten5}"
        )

        # ----------------------------------------------------------------------
        # F6: STT Homophones (Naiken/Property Viewing vs Naiken/Inspection)
        # ----------------------------------------------------------------------
        q6 = "島田さんは何の内検を希望していましたか？" # "内検" (Naiken) homophone of "内見" (Naiken - viewing)
        ans6, meta6 = await self.orchestrator.handle(sid, q6)
        rewritten6 = meta6.get("rewritten_query", "")
        
        # The homophone should be corrected or mapped to "内見"
        passed6 = "内見" in rewritten6 or "内見" in ans6
        await self.record_result(
            "F_Fuzzy_Matching", "F6_STT_HOMOPHONES",
            q6, ans6, rewritten6, meta6, passed6,
            error=None if passed6 else f"Homophone '内検' was not resolved to '内見'. Rewrite: {rewritten6}"
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

        # Use "同氏" (pronoun in config but NOT in SINGULAR_PRONOUNS) to bypass Tier 1 Heuristics and test Tier 2 History limit
        q5 = "同氏が気にした理由は何ですか？" # Turn 49: referring to Shimada (GT_03)
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

        # ----------------------------------------------------------------------
        # B3 & B4: Context Interruption Switch-back & Compound Pronouns
        # ----------------------------------------------------------------------
        sid_switch = "v5_switchback_test"
        await self.clear_db(sid_switch)
        
        # Seed both GT_11 (Sato) and GT_03 (Shimada) caches
        async with self.db_pool.acquire() as conn:
            c_sato = await upsert_cache_slot(
                conn, sid_switch, "GT_11_topic", "RAG", "heuristics",
                {"documents": [{"chunk_id": "c11", "text": "佐藤太郎さんはアセットジャパンの営業担当者です。"}]},
                {"entity_id": "GT_11", "entity_type": "meeting_transcript"}
            )
            c_shimada = await upsert_cache_slot(
                conn, sid_switch, "GT_03_topic", "RAG", "heuristics",
                {"documents": [{"chunk_id": "c3", "text": "島田さんは物件の内見を希望しています。"}]},
                {"entity_id": "GT_03", "entity_type": "meeting_transcript"}
            )
            # Add entity index records
            await conn.execute("""
                INSERT INTO session_entity_index (session_id, cache_slot_id, entity_id, entity_type, display_names)
                VALUES ($1, $2, 'GT_11_佐藤太郎', 'person', ARRAY['佐藤太郎', '佐藤']),
                       ($1, $3, 'GT_03_島田', 'person', ARRAY['島田', 'しまだ'])
            """, sid_switch, c_sato, c_shimada)
            
        # Turn 1: Query about Sato
        q_sato = "GT_11 of 佐藤さんについて教えてください。"
        _, meta_sato = await self.orchestrator.handle(sid_switch, q_sato)
        
        # Turn 2: Query about Shimada (interrupting / switching topic)
        q_shimada = "やっぱりキャンセルして、GT_03 of 島田さんについて教えてください。"
        _, meta_shimada = await self.orchestrator.handle(sid_switch, q_shimada)
        
        # Turn 3: Compound Pronoun Resolution (Pronoun + Proper noun comparison)
        # Active topic is Shimada. Compare "同氏" (Shimada) and "佐藤太郎さん".
        q_compound = "同氏と佐藤太郎さんは同じ会社に所属していますか？"
        ans_compound, meta_compound = await self.orchestrator.handle(sid_switch, q_compound)
        rewritten_compound = meta_compound.get("rewritten_query", "")
        
        resolved_shimada = "島田" in rewritten_compound or "GT_03" in rewritten_compound
        resolved_sato = "佐藤" in rewritten_compound or "GT_11" in rewritten_compound
        
        # Comparison of multiple entities should bypass cache (needs_retrieval=full)
        passed_b4 = resolved_shimada and resolved_sato and meta_compound.get("needs_retrieval") == "full"
        
        await self.record_result(
            "B_History_Bloat", "B4_COMPOUND_PRONOUN_RESOLUTION",
            q_compound, ans_compound, rewritten_compound, meta_compound, passed_b4,
            error=None if passed_b4 else f"Compound resolution failed. Shimada resolved: {resolved_shimada}, Sato resolved: {resolved_sato}, Retrieval: {meta_compound.get('needs_retrieval')}"
        )
        
        # Turn 4: Query switching back to Sato (using switchback keyword)
        q_switch = "やっぱり忘れて、最初の佐藤さんの話に戻りましょう。"
        ans_switch, meta_switch = await self.orchestrator.handle(sid_switch, q_switch)
        rewritten_switch = meta_switch.get("rewritten_query", "")
        
        passed_b3 = (
            meta_switch.get("target_topic_key") == "GT_11_topic" and
            meta_switch.get("needs_retrieval") == "none"
        )
        
        await self.record_result(
            "B_History_Bloat", "B3_CONTEXT_INTERRUPTION_SWITCHBACK",
            q_switch, ans_switch, rewritten_switch, meta_switch, passed_b3,
            error=None if passed_b3 else f"Switchback failed. Target: {meta_switch.get('target_topic_key')}, Retrieval: {meta_switch.get('needs_retrieval')}"
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
