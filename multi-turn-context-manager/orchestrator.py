import asyncio
import time
import json
import logging
import re
from session_lock import SessionLockManager
from router import Router, LLMManager, _safe_embed, extract_json
from cache_manager import get_cache_slot, touch_cache_slot, upsert_cache_slot, update_cache_slot, check_cache_ttl
from entity_extractor import EntityExtractor
from engines import SQLEngine, RAGEngine, WebEngine, EngineCircuitBreaker, EngineResult

logger = logging.getLogger(__name__)

def should_use_direct_path(pipeline: str, payload: dict, needs_retrieval: str) -> bool:
    """
    Determines if a request qualifies for the Direct-Answer Path.
    """
    if needs_retrieval == "partial":
        return False
        
    if pipeline == "SQL":
        rows = payload.get("rows", [])
        return len(rows) == 1 and len(rows[0].keys()) <= 3
    elif pipeline == "WEB":
        results = payload.get("results", [])
        return len(results) == 1 and results[0].get("relevance", 0) > 0.85
    return False

def format_direct_sql_response(payload: dict) -> str:
    rows = payload.get("rows", [])
    if not rows:
        return "該当するデータが見つかりませんでした。"
    row = rows[0]
    items = []
    for k, v in row.items():
        friendly_key = k.replace("_", " ").title()
        if "duration" in k:
            friendly_key = "通話時間"
            v = f"{v}秒"
        elif "meeting_date" in k or "date" in k:
            friendly_key = "日付"
        elif "summary" in k:
            friendly_key = "要約"
        elif "speaker" in k:
            friendly_key = "話者"
        elif "participants" in k:
            friendly_key = "参加者"
        items.append(f"{friendly_key}: {v}")
    return ", ".join(items) + "。"

def format_direct_web_response(payload: dict) -> str:
    results = payload.get("results", [])
    if not results:
        return "該当する検索結果が見つかりませんでした。"
    return results[0]["snippet"]

class IntelligentOrchestrator:
    def __init__(self, db_pool, llm_manager: LLMManager, embedding_model):
        self.db_pool = db_pool
        self.llm_manager = llm_manager
        self.embedding_model = embedding_model
        
        self.lock_manager = SessionLockManager()
        self.router = Router(db_pool, llm_manager, embedding_model)
        self.entity_extractor = EntityExtractor(db_pool, llm_manager)
        
        # Initialize engines and wrap them in circuit breakers
        self.sql_engine = EngineCircuitBreaker(SQLEngine(db_pool, llm_manager))
        self.rag_engine = EngineCircuitBreaker(RAGEngine(db_pool, embedding_model))
        self.web_engine = EngineCircuitBreaker(WebEngine(llm_manager))

    async def handle(self, session_id: str, query: str, lock_timeout: float = 8.0) -> tuple[str, dict]:
        """
        Coordinates the 8-step pipeline for multi-turn context management.
        """
        conn = None
        tx = None
        try:
            start_time = time.perf_counter()
            # Step 1: Session Lock
            conn = await self.db_pool.acquire()
            tx = conn.transaction()
            await tx.start()

            # Acquire transaction advisory lock
            await self.lock_manager.acquire_lock(conn, session_id, timeout=lock_timeout)
            
            # Step 2 & 3: Fetch Metadata and Route
            route_result = await self.router.route(session_id, query)
            
            needs_retrieval = route_result["needs_retrieval"]
            use_cache = route_result["use_cache"]
            target_topic_key = route_result["target_topic_key"]
            target_pipeline = route_result["target_pipeline"]
            rewritten_query = route_result["rewritten_query"]
            partial_params = route_result.get("partial_fetch_params")
            
            logger.info(f"Orchestrator Decision: needs_retrieval={needs_retrieval}, target_pipeline={target_pipeline}, target_topic_key={target_topic_key}")
            
            payload = {}
            summary_context = {}
            
            # Step 4: Execution & Retrieval
            if needs_retrieval == "none" and use_cache:
                # Cache Hit: Read from Cold Table
                cache_slot = await get_cache_slot(conn, session_id, target_topic_key)
                if cache_slot:
                    payload = cache_slot["payload"] or {}
                    summary_context = cache_slot["summary_context"] or {}
                    # Touch cache slot
                    await touch_cache_slot(conn, session_id, target_topic_key)
                else:
                    logger.warning(f"Cache slot '{target_topic_key}' not found in database despite router hit. Forcing full retrieval.")
                    needs_retrieval = "full"
                    
            if needs_retrieval == "partial":
                # Partial Fetch: Lock Hot slot row, read old payload, and retrieve additional data
                cache_slot = await get_cache_slot(conn, session_id, target_topic_key)
                if not cache_slot:
                    logger.warning(f"Cache slot '{target_topic_key}' not found in database for partial fetch. Falling back to full retrieval.")
                    needs_retrieval = "full"
                else:
                    old_payload = cache_slot["payload"] if cache_slot else {}
                    
                    # Run target engine with partial filter params
                    engine_res = await self._run_engine(
                        target_pipeline, query, session_id=session_id, partial_params=partial_params
                    )
                    payload = engine_res.payload
                    
                    # Merge or supplement payload (simple override or merge if dict)
                    if isinstance(old_payload, dict) and isinstance(payload, dict):
                        merged_payload = {**old_payload, **payload}
                        payload = merged_payload
                    
                    # Step 5: Entity Indexing
                    summary_context = await self._build_summary_context(target_pipeline, payload, rewritten_query=rewritten_query or query)
                    await self.entity_extractor.extract_and_index(conn, session_id, cache_slot["id"], target_pipeline, payload, query=rewritten_query or query)
                    
                    # Step 6: Cache Update with new embedding
                    new_emb = await _safe_embed(rewritten_query, self.embedding_model)
                    await update_cache_slot(conn, session_id, target_topic_key, payload, summary_context, query_embedding=new_emb)
                
            if needs_retrieval == "full":
                # Topic Shift / New Query: Run engine from scratch
                if not target_topic_key:
                    # Generate a new topic key if not set
                    target_topic_key = f"{target_pipeline.lower()}_{int(time.time())}"
                    
                engine_res = await self._run_engine(
                    target_pipeline, rewritten_query, session_id=session_id
                )
                payload = engine_res.payload
                summary_context = await self._build_summary_context(target_pipeline, payload, rewritten_query=rewritten_query or query)
                
                # Upsert cache slot (which does LRU check and Cascade insert)
                new_emb = await _safe_embed(rewritten_query, self.embedding_model)
                cache_slot_id = await upsert_cache_slot(
                    conn, session_id, target_topic_key, target_pipeline, route_result["routing_method"], payload, summary_context, query_embedding=new_emb
                )
                
                # Step 5: Entity Indexing
                await self.entity_extractor.extract_and_index(conn, session_id, cache_slot_id, target_pipeline, payload, query=rewritten_query or query)

            # Step 7: Answer Generation
            direct_answer_used = should_use_direct_path(target_pipeline, payload, needs_retrieval)
            
            if direct_answer_used:
                logger.info("Direct-Answer Path activated.")
                if target_pipeline == "SQL":
                    answer = format_direct_sql_response(payload)
                elif target_pipeline == "WEB":
                    answer = format_direct_web_response(payload)
                else:
                    answer = "Direct answer template not found."
                
                self_check_passed = True
                self_check_retries = 0
                answer_confidence = "high"
            else:
                logger.info(f"LLM Path activated. Generating response using {self.llm_manager.__class__.__name__}...")
                answer, answer_confidence, self_check_passed, self_check_retries = await self._generate_llm_answer_with_self_check(
                    query, rewritten_query, target_pipeline, payload
                )
                
            # Step 8: Log and Commit
            # Save to chat history
            routing_metadata = {
                "routing_tier": route_result["routing_tier"],
                "routing_method": route_result["routing_method"],
                "embedding_failed": route_result["embedding_failed"],
                "direct_answer_used": direct_answer_used,
                "self_check_retries": self_check_retries,
                "needs_retrieval": needs_retrieval,
                "target_pipeline": target_pipeline,
                "target_topic_key": target_topic_key
            }
            
            await conn.execute("""
                INSERT INTO chat_history (session_id, role, content, rewritten_content, answer_confidence, routing_metadata)
                VALUES ($1, 'user', $2, $3, 'high', $4)
            """, session_id, query, rewritten_query, json.dumps(routing_metadata))
            
            await conn.execute("""
                INSERT INTO chat_history (session_id, role, content, answer_confidence, routing_metadata)
                VALUES ($1, 'assistant', $2, $3, $4)
            """, session_id, answer, answer_confidence, json.dumps(routing_metadata))
            
            # Commit the transaction
            await tx.commit()
            
            end_time = time.perf_counter()
            latency = (end_time - start_time) * 1000
            
            metadata = {
                "rewritten_query": rewritten_query,
                "needs_retrieval": needs_retrieval,
                "relation_type": route_result.get("relation_type"),
                "target_pipeline": target_pipeline,
                "target_topic_key": target_topic_key,
                "routing_tier": route_result["routing_tier"],
                "routing_method": route_result["routing_method"],
                "embedding_failed": route_result["embedding_failed"],
                "direct_answer_used": direct_answer_used,
                "self_check_passed": self_check_passed,
                "self_check_retries": self_check_retries,
                "answer_confidence": answer_confidence,
                "latency_ms": latency
            }
            
            return answer, metadata
            
        except asyncio.TimeoutError as e:
            logger.error(f"Timeout handling query: {e}")
            if tx is not None:
                try:
                    await asyncio.shield(tx.rollback())
                except Exception:
                    pass
            raise e
        except Exception as e:
            logger.error(f"Error handling query: {e}", exc_info=True)
            if tx is not None:
                try:
                    await asyncio.shield(tx.rollback())
                except Exception:
                    pass
            raise e
        except BaseException as e:
            logger.error(f"BaseException (e.g. CancelledError) handling query: {e}")
            if tx is not None:
                try:
                    await asyncio.shield(tx.rollback())
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass
            raise e
        finally:
            if conn is not None:
                try:
                    await asyncio.shield(self.db_pool.release(conn))
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass

    async def _run_engine(self, pipeline: str, query: str, **kwargs) -> EngineResult:
        """
        Helper to run the appropriate execution engine wrapped by Circuit Breaker.
        """
        if pipeline == "SQL":
            return await self.sql_engine.execute(query, **kwargs)
        elif pipeline == "RAG":
            return await self.rag_engine.execute(query, **kwargs)
        elif pipeline == "WEB":
            return await self.web_engine.execute(query, **kwargs)
        else:
            # MODEL pipeline
            return EngineResult(
                source="parametric_knowledge",
                payload={"query_used": query, "info": "No specific database retrieval performed for this general query."}
            )

    async def _build_summary_context(self, pipeline: str, payload: dict, rewritten_query: str = None) -> dict:
        """
        Helper to construct the summary_context metadata for the Hot table.
        """
        summary = {"entity_type": "sql_result", "entity_id": "general", "display_name": "Metadata summary", "key_attributes": {}}
        if pipeline == "SQL":
            rows = payload.get("rows", [])
            if rows:
                # Check if it has GT_XX session format
                session_id = None
                for val in rows[0].values():
                    if isinstance(val, str) and re.match(r'^GT_\d+$', val):
                        session_id = val
                        break
                if session_id:
                    summary = {
                        "entity_type": "meeting_transcript",
                        "entity_id": session_id,
                        "display_name": f"{session_id}の通話",
                        "key_attributes": {
                            "participants": rows[0].get("participants", [])
                        }
                    }
        elif pipeline == "RAG":
            docs = payload.get("documents", [])
            if docs:
                chunk_id = docs[0].get("chunk_id")
                meta = docs[0].get("metadata", {})
                doc_id = meta.get("doc_id", "doc_general")
                summary = {
                    "entity_type": "document",
                    "entity_id": doc_id,
                    "display_name": f"{doc_id}のドキュメント",
                    "key_attributes": {
                        "chunk_id": chunk_id,
                        "source_table": meta.get("source_table")
                    }
                }
        elif pipeline == "WEB":
            results = payload.get("results", [])
            if results:
                summary = {
                    "entity_type": "document",
                    "entity_id": "web_search",
                    "display_name": results[0].get("title", "Web search result"),
                    "key_attributes": {
                        "url": results[0].get("url")
                    }
                }

        # Parse dates and GTs from rewritten_query if available to prevent metadata staleness
        if rewritten_query:
            gts = re.findall(r'GT_\d+', rewritten_query, re.IGNORECASE)
            dates = re.findall(r'\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b', rewritten_query)
            if gts:
                gts_upper = [gt.upper() for gt in gts]
                summary["entity_type"] = "meeting_transcript"
                if len(gts) > 1:
                    summary["entity_id"] = gts_upper[0]  # default to first as primary ID
                    summary["display_name"] = ", ".join(gts_upper) + "の通話"
                else:
                    summary["entity_id"] = gts_upper[0]
                    summary["display_name"] = f"{gts_upper[0]}の通話"
                
                if "key_attributes" not in summary:
                    summary["key_attributes"] = {}
                summary["key_attributes"]["gt_sessions"] = gts_upper

            if dates:
                d_str, m_str, y_str = dates[0]
                y = int(y_str) if y_str else 2026
                if y < 100:
                    y += 2000
                dt_str = f"{y}-{int(m_str):02d}-{int(d_str):02d}"
                if "key_attributes" not in summary:
                    summary["key_attributes"] = {}
                summary["key_attributes"]["date"] = dt_str
                
        return summary

    async def _generate_llm_answer_with_self_check(self, original_query: str, rewritten_query: str, pipeline: str, payload: dict) -> tuple[str, str, bool, int]:
        """
        Generates final answer using the LLM and performs Self-Check Verification.
        """
        context_str = json.dumps(payload, ensure_ascii=False, indent=2)
        
        # Determine if context is likely empty or error
        context_empty = False
        if not payload or (isinstance(payload, dict) and (not payload.get("rows") and not payload.get("documents") and not payload.get("results") and not payload.get("response"))):
            context_empty = True
            
        system_prompt = (
            "あなたはスマートで親切なAIアシスタントのJavisです。\n"
            "あなたの任務は、提供されたコンテキスト（Context）に基づいて、ユーザーの質問に答えることです。\n\n"
            "[CONTEXT]\n"
            f"{context_str}\n\n"
            "【重要なルール】\n"
            "1. コンテキスト内の情報のみに基づいて答えてください。コンテキストにない情報を付け加えたり、データを捏造（ハルシネーション）したりしないでください。\n"
            "2. コンテキストに情報が含まれていない場合、または不十分な場合は、正直に「申し訳ありませんが、提供された資料からはその情報を確認できませんでした」という旨を伝えてください。\n"
            "3. 自分の知識（学習データ）を使って勝手に補完しないでください。\n"
            "4. 回答は日本語で行ってください。"
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": original_query}
        ]
        
        retries = 0
        max_retries = 2
        
        while retries <= max_retries:
            try:
                response = await self.llm_manager.generate_chat_completion(messages=messages)
                
                # Verify the response
                passed, issues = await self._verify_hallucination(response, context_str)
                if passed:
                    return response, "high", True, retries
                    
                retries += 1
                if retries <= max_retries:
                    logger.warning(f"Self-check failed: {issues}. Retrying ({retries}/{max_retries})...")
                    # Append correction prompt
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": f"検証エンジンがエラーを検出しました: {issues}。コンテキストに基づいて、正確で事実に基づいた回答を再生成してください。情報がない場合は、無理に答えず情報がないことを伝えてください。"
                    })
                else:
                    disclaimer = "\n\n*(注意: この回答は自己検証で完全に一致しなかったため、信頼性が低くなっています。)*"
                    return response + disclaimer, "low", False, max_retries
            except asyncio.TimeoutError:
                if retries < max_retries:
                    retries += 1
                    logger.warning(f"LLM Answer generation timed out. Retrying ({retries}/{max_retries})...")
                    continue
                else:
                    return "申し訳ありません。回答の生成中にタイムアウトが発生しました。時間をおいて再度お試しください。", "low", False, retries
            except Exception as e:
                logger.error(f"Error in LLM answer generation: {e}")
                return f"エラーが発生しました: {str(e)}", "low", False, retries

    async def _verify_hallucination(self, response: str, context_str: str) -> tuple[bool, str]:
        """
        Verification step: checks if the response contradicts or exaggerates details in the context.
        """
        system_prompt = (
            "あなたはプロのAI検証担当（Verifier）です。AIアシスタントの回答が、提供された生データ（Context）に対して誠実かつ正確であるかを確認してください。\n\n"
            "【合格 (passed: true) と判定すべきケース】\n"
            "1. 回答内容がすべてコンテキスト内の事実に基づいている。\n"
            "2. コンテキストに情報がない、または不足している場合に、AIが「確認できませんでした」「データがありません」と正直に回答している。（これはハルシネーションではありません）\n"
            "3. AIが「コンテキストに基づくと〜」と前置きして、コンテキストの範囲内でのみ答えている。\n\n"
            "【不合格 (passed: false) と判定すべきケース】\n"
            "1. コンテキストにない数値を答えたり、存在しない人名や出来事を捏造している。\n"
            "2. コンテキストの内容と明らかに矛盾する回答をしている。\n"
            "3. 「わからない」と答えるべきなのに、自分の学習データから勝手に情報を補完して事実として伝えている。\n\n"
            "[CONTEXT (生データ)]\n"
            f"{context_str}\n\n"
            "[AI ASSISTANT RESPONSE]\n"
            f"{response}\n\n"
            "出力形式（JSONのみ）：\n"
            "{\n"
            "  \"passed\": boolean,\n"
            "  \"issues\": \"不合格の場合の具体的な理由。合格なら null\"\n"
            "}"
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "上記の回答を検証してください。"}
        ]
        
        try:
            verdict_text = await self.llm_manager.generate_chat_completion(
                messages=messages, response_format={"type": "json_object"}
            )
            verdict = extract_json(verdict_text)
            return verdict.get("passed", True), verdict.get("issues")
        except Exception as e:
            logger.error(f"Error during self-check verification: {e}")
            # If verifier fails, default to True to avoid infinite retry loop
            return True, None
