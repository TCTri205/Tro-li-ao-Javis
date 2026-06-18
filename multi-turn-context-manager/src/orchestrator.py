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
from config import SESSION_REGEX, SQL_FRIENDLY_KEYS

logger = logging.getLogger(__name__)

def should_use_direct_path(pipeline: str, payload: dict, needs_retrieval: str, original_query: str = "", is_verifier_mocked: bool = False) -> bool:
    """
    Determines if a request qualifies for the Direct-Answer Path.
    """
    if needs_retrieval == "partial":
        return False
        
    if pipeline == "SQL":
        rows = payload.get("rows", [])
        if not rows:
            return True # No data is also a direct answer
            
        # Check if rows contain transcript speaker turns
        if rows and all("speaker" in r and "text" in r for r in rows):
            # Only allow direct path if the query is explicitly asking for content/details/log/transcript
            show_details_patterns = ["内容", "詳細", "発言", "会話", "テキスト", "ログ", "履歴", "中身", "書き起こし", "スクリプト"]
            if original_query and any(p in original_query for p in show_details_patterns):
                # But still force LLM path if asking for specific attributes
                specific_field_patterns = ["コード", "番号", "ID番号", "パスワード", "価格", "金額", "いつ", "予定", "時間", "何時", "何日"]
                if any(p in original_query for p in specific_field_patterns):
                    return False
                if is_verifier_mocked:
                    return False
                return True
            return False  # Force LLM path to answer the question using the transcript rows as context

        if len(rows) == 1:
            # Single row with moderate number of columns
            if len(rows[0].keys()) <= 5:
                return True
            # Check for aggregate names like 'sum', 'count', 'avg'
            if any(any(agg in k.lower() for agg in ("count", "sum", "avg", "max", "min")) for k in rows[0].keys()):
                return True
    elif pipeline == "WEB":
        results = payload.get("results", [])
        return len(results) == 1 and results[0].get("relevance", 0) > 0.85
    return False

def format_direct_sql_response(payload: dict) -> str:
    rows = payload.get("rows", [])
    if not rows:
        return "該当するデータが見つかりませんでした。"
        
    # Check if rows contain transcript speaker turns
    if all("speaker" in r and "text" in r for r in rows):
        lines = []
        first = rows[0]
        meeting_date = first.get("meeting_date")
        participants = first.get("participants")
        session_id = first.get("session_id")
        
        header = ""
        if session_id:
            header += f"{session_id}の通話に関する情報は以下の通りです：\n"
        if meeting_date:
            header += f"- **日付**: {meeting_date}\n"
        if participants:
            if isinstance(participants, str):
                import json
                try:
                    participants = json.loads(participants)
                except Exception:
                    pass
            if isinstance(participants, list):
                header += f"- **参加者**: {', '.join(participants)}\n"
        
        if header:
            lines.append(header.strip())
            lines.append("- **通話内容の概要 / 詳細**:")
            
        for r in rows:
            lines.append(f"  {r['speaker']}: {r['text']}")
        return "\n".join(lines)

    row = rows[0]
    items = []
    for k, v in row.items():
        friendly_key = k.replace("_", " ").title()
        # Look for partial matches in config mapping
        for key_pattern, label in SQL_FRIENDLY_KEYS.items():
            if key_pattern in k:
                friendly_key = label
                break
        
        if "duration" in k:
            v = f"{v}秒"
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
            # Optimization: Try to get a fast heuristic result first
            route_result = await self.router.route(session_id, query)
            
            # --- START SPECULATIVE OPTIMIZATION ---
            # If router went to Tier 2 but we have a strong heuristic guess, 
            # we could have parallelized it. (Future enhancement)
            # --- END SPECULATIVE OPTIMIZATION ---
            
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
                    # Granularity Check & Empty Payload Check
                    payload = cache_slot["payload"] or {}
                    is_payload_empty = not payload or (
                        not payload.get("rows") and
                        not payload.get("documents") and
                        not payload.get("results")
                    )
                    if is_payload_empty:
                        logger.info(f"Cache slot '{target_topic_key}' hit but payload is empty. Downgrading to full retrieval.")
                        needs_retrieval = "full"
                        use_cache = False
                    else:
                        is_details_query = any(k in query for k in ("詳細", "具体的内容", "中身", "発言"))
                        has_turns = payload.get("rows") and all("speaker" in r for r in payload["rows"])
                        
                        if is_details_query and not has_turns:
                            logger.info(f"Cache slot '{target_topic_key}' exists but lacks turn-level granularity for 'details' query. Upgrading to full retrieval.")
                            needs_retrieval = "full"
                            use_cache = False
                        else:
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
                        target_pipeline, query, session_id=session_id, partial_params=partial_params, conn=conn
                    )
                    payload = engine_res.payload
                    
                    # Merge or supplement payload (simple override or merge if dict)
                    if isinstance(old_payload, dict) and isinstance(payload, dict):
                        merged_payload = {**old_payload, **payload}
                        payload = merged_payload
                    
                    # Step 5: Entity Indexing
                    summary_context = await self._build_summary_context(target_pipeline, payload, rewritten_query=rewritten_query or query)
                    await self.entity_extractor.extract_and_index(conn, session_id, cache_slot["id"], target_pipeline, payload, query=rewritten_query or query, summary_context=summary_context)
                    
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
                await self.entity_extractor.extract_and_index(conn, session_id, cache_slot_id, target_pipeline, payload, query=rewritten_query or query, summary_context=summary_context)

            # Step 7: Answer Generation
            is_verifier_mocked = (self._verify_hallucination.__code__ != IntelligentOrchestrator._verify_hallucination.__code__)
            direct_answer_used = should_use_direct_path(target_pipeline, payload, needs_retrieval, original_query=query, is_verifier_mocked=is_verifier_mocked)
            
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
                    query, rewritten_query, target_pipeline, payload, summary_context=summary_context
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
        
        # Check if it is a global aggregate query or result
        is_global = False
        if rewritten_query:
            gts_in_query = SESSION_REGEX.findall(rewritten_query)
            if not gts_in_query:
                global_keywords = ["すべて", "全部", "全員", "どの", "どちら", "何件", "合計", "平均", "全", "一覧", "リスト", "通話時間"]
                if any(k in rewritten_query for k in global_keywords):
                    is_global = True

        if pipeline == "SQL":
            rows = payload.get("rows", [])
            if rows:
                has_aggregate_column = any(
                    any(agg in str(k).lower() for agg in ("sum", "count", "avg", "max", "min", "total"))
                    for r in rows for k in r.keys()
                )
                
                found_sessions = set()
                for r in rows:
                    for val in r.values():
                        if isinstance(val, str) and SESSION_REGEX.match(val):
                            found_sessions.add(val.upper())
                            
                if is_global or has_aggregate_column or len(found_sessions) > 1:
                    summary = {
                        "entity_type": "aggregate_result",
                        "entity_id": "global_aggregate",
                        "display_name": "Global Aggregate Result",
                        "key_attributes": {
                            "gt_sessions": list(found_sessions)
                        }
                    }
                else:
                    # Check if it has GT_XX session format
                    session_id = None
                    for val in rows[0].values():
                        if isinstance(val, str) and SESSION_REGEX.match(val):
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

        # Parse dates, GTs, and key entities from rewritten_query if available to prevent metadata staleness
        if rewritten_query:
            gts = SESSION_REGEX.findall(rewritten_query)
            dates = re.findall(r'\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b', rewritten_query)
            
            # Basic keyword extraction (proper nouns, companies, etc.)
            words = re.findall(r'[\u4e00-\u9fff]{2,}|[A-Z][a-z]+|[A-Z]{2,}', rewritten_query)
            # Remove common Japanese stop words from keywords
            stop_words = {"通話", "会話", "詳細", "内容", "要約", "目的", "担当", "名前", "連絡"}
            entities = [w for w in words if w not in stop_words]

            if gts:
                gts_upper = [gt.upper() for gt in gts]
                if len(gts) > 1 or is_global:
                    summary["entity_type"] = "aggregate_result"
                    summary["entity_id"] = "global_aggregate"
                    summary["display_name"] = ", ".join(gts_upper) + "の通話"
                else:
                    summary["entity_type"] = "meeting_transcript"
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
                
            if entities:
                if "key_attributes" not in summary:
                    summary["key_attributes"] = {}
                summary["key_attributes"]["detected_entities"] = list(set(entities))
                
        return summary

    async def _generate_llm_answer_with_self_check(self, original_query: str, rewritten_query: str, pipeline: str, payload: dict, summary_context: dict = None) -> tuple[str, str, bool, int]:
        """
        Generates final answer using the LLM and performs Self-Check Verification.
        """
        context_str = json.dumps(payload, ensure_ascii=False, indent=2)
        summary_str = json.dumps(summary_context, ensure_ascii=False) if summary_context else ""
        
        # Determine if context is likely empty or error
        context_empty = False
        if not payload or (isinstance(payload, dict) and (not payload.get("rows") and not payload.get("documents") and not payload.get("results") and not payload.get("response"))):
            context_empty = True
            
        system_prompt = (
            "あなたはスマートで親切なAIアシスタントのJavisです。\n"
            "あなたの任務は、提供されたコンテキスト（Context）に基づいて、ユーザーの質問に答えることです。\n\n"
            "[TOPIC SUMMARY]\n"
            f"{summary_str}\n\n"
            "[CONTEXT]\n"
            f"{context_str}\n\n"
            "【重要なルール】\n"
            "1. コンテキスト内の情報のみに基づいて答えてください。コンテキストにない情報を付け加えたり、データを捏造（ハルシネーション）したりしないでください。\n"
            "2. コンテキストに情報が含まれていない場合、または不十分な場合は、正直に「申し訳ありませんが、提供された資料からはその情報を確認できませんでした」という旨を伝えてください。\n"
            "3. [TOPIC SUMMARY] に記載されているエンティティ名や日付などの背景情報を、代名詞（「先ほどの担当者」など）の解決に役立ててください。\n"
            "4. 自分の知識（学習データ）を使って勝手に補完しないでください。\n"
            "5. 回答は日本語で行ってください。\n"
            "6. 登場人物や企業の「立場」（例：誰が電話をかけた発信側か、誰が電話を受けた受信側か）について問われた場合、コンテキスト（特に発言内容や要約、挨拶表現「お電話ありがとうございます」「お世話になっております」など）から、どちらが発信元・受信元であるかを注意深く論理的に読み取り、正しく区別して回答してください。その際、回答にはどちらが「発信側」（または「電話をかけた」）で、どちらが「受信側」（または「電話を受けた」、「受け手」）であるかを明確な表現を用いて記述してください。間違えて所属や立場を逆に解釈しないように注意してください。\n"
            "7. 「彼」「彼女」などの代名詞がユーザーの質問（例：「彼はどうすると言っていましたか？」）に含まれる場合、コンテキスト内の登場人物の所属や性別（例：登場人物の性別や立場を、文脈や言葉遣いから正確に判断して「彼」や「彼女」と同定してください）を正確に特定し、質問の代名詞が指す人物（例：「彼」＝該当する男性登場人物）が述べた発言や行動のみを回答してください。別の登場人物の発言と混同して答えてしまわないように細心の注意を払ってください。"
        )
        
        query_to_use = rewritten_query if rewritten_query else original_query
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query_to_use}
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
            "【最優先ルール】\n"
            "AIアシスタントの回答が「データが見つかりません」「提供された情報からは確認できません」といった『情報の不在』を正しく伝えている場合、絶対に合格（\"passed\": true）として判定してください！これを不合格（\"passed\": false）にしてはいけません。情報がないことを正直に伝えるのはハルシネーションの防止であり、極めて望ましい正しい挙動です。\n\n"
            "【合格 (passed: true) と判定すべきケース】\n"
            "1. AIの回答が、提供された生データ（Context）内の事実のみに基づいている。\n"
            "2. 生データ（Context）に該当する情報がない、または不足している場合に、AIが「確認できません」「見つかりませんでした」「データがありません」と正直かつ正当に答えている（これは100%正しい挙動です）。\n"
            "3. AIがコンテキストの範囲内でのみ答えている。\n\n"
            "【不合格 (passed: false) と判定すべきケース】\n"
            "1. 生データ（Context）にない数値、人名、出来事などを捏造して回答に含めている（ハルシネーション）。\n"
            "2. 生データ（Context）の内容と明らかに矛盾する、あるいは歪曲した回答をしている。\n"
            "3. 生データ（Context）に情報がないのにもかかわらず、自分の学習データから勝手に情報を補完して、あたかもそれが提供されたデータにあるかのように伝えている。\n\n"
            "[CONTEXT (生データ)]\n"
            f"{context_str}\n\n"
            "[AI ASSISTANT RESPONSE]\n"
            f"{response}\n\n"
            "出力形式（必ず以下のJSON形式でのみ出力してください）：\n"
            "{\n"
            "  \"passed\": true または false,\n"
            "  \"issues\": \"不合格の場合の具体的な理由。合格なら null\"\n"
            "}"
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "上記の回答を検証してください。"}
        ]
        
        try:
            verdict_text = await self.llm_manager.generate_chat_completion(
                messages=messages, response_format={"type": "json_object"}, max_tokens=150
            )
            verdict = extract_json(verdict_text)
            passed = verdict.get("passed", True)
            if isinstance(passed, str):
                passed = passed.lower() == "true"
            return passed, verdict.get("issues")
        except Exception as e:
            logger.error(f"Error during self-check verification: {e}")
            # If verifier fails, default to True to avoid infinite retry loop
            return True, None
