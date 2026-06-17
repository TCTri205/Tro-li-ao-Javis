import asyncio
import os
import re
import json
import logging
import time
import numpy as np
from datetime import datetime, timezone
from sentence_transformers import SentenceTransformer
from groq import AsyncGroq
from openai import AsyncOpenAI
import httpx
from session_lock import get_lock_id

logger = logging.getLogger(__name__)

# Heuristic keywords for switching in Japanese (e.g. "やっぱり", "別の話", "スキップ")
SWITCH_KEYWORDS_PATTERN = re.compile(r'(やっぱり|別の話|キャンセル|スキップ|忘れて)', re.IGNORECASE)

# Japanese pronouns / indicator words to look for in query
PRONOUNS = [
    "それ", "あれ", "これ", "そちら", "あちら", "こちら", 
    "彼", "彼女", "彼ら", "彼女ら", "その人", "あの人", "この人",
    "さっき", "先ほど", "さきほど", "先程", "前回の", "さっきの", "先ほどの",
    "このファイル", "そのファイル", "あのファイル",
    "このドキュメント", "そのドキュメント", "あのドキュメント",
    "この通話", "その通話", "あの通話", "先ほどの通話", "さっきの通話",
    "この会話", "その会話", "あの会話", "先ほどの会話", "さっきの会話",
    "その件", "あの件", "この件", "その話", "あの話", "この話",
    "そのcall", "このcall", "あのcall", "さっきのcall", "先ほどのcall", "call", "通話",
    "その", "この", "あの", "その物件", "この物件", "あの物件",
    "同物件", "同通話", "同氏", "同社"
]


async def _safe_embed(query: str, model: SentenceTransformer) -> list:
    """
    Safely compute the embedding of the query with a 1.0s timeout and a zero-vector check.
    """
    try:
        prefixed_query = f"query: {query}"
        loop = asyncio.get_running_loop()
        # Run synchronous model.encode in a separate thread to prevent blocking the async loop
        vector = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: model.encode(prefixed_query)),
            timeout=1.0
        )
        if vector is None:
            raise ValueError("Embedding model returned None")
        vector_list = vector.tolist()
        if all(x == 0 for x in vector_list):
            raise ValueError("Embedding model returned zero vector")
        return vector_list
    except Exception as e:
        logger.warning(f"_safe_embed failed: {str(e)}")
        return None

def extract_json(text: str) -> dict:
    """
    Extract a JSON block from the LLM output safely.
    """
    if "<think>" in text or "</think>" in text:
        if "</think>" in text:
            text = text.split("</think>")[-1].strip()
        else:
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
            
    try:
        return json.loads(text.strip())
    except Exception:
        pass
    
    # Try markdown json blocks
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except Exception:
            pass
            
    # Try finding the first '{' and last '}'
    match_braces = re.search(r'(\{.*\})', text, re.DOTALL)
    if match_braces:
        try:
            return json.loads(match_braces.group(1).strip())
        except Exception:
            pass
            
    raise ValueError("Failed to extract valid JSON from LLM response")

def heuristic_pipeline_guess(query: str) -> str:
    """
    Simple keyword heuristic to guess the target pipeline for a Japanese query.
    """
    query_lower = query.lower()
    
    # Check Japanese SQL keywords
    sql_keywords = [
        "選択", "カウント", "平均", "時間", "通話", "日付", "何時", "誰", "秒", "分", "通話時間", 
        "だれ", "何秒", "何分", "件数", "何件", "いつ", "何日"
    ]
    # Check Japanese RAG keywords
    rag_keywords = [
        "要約", "内容", "詳細", "発言", "翻訳", "ドキュメント", "ファイル", "テキスト", "何を話した", 
        "訳", "内見", "契約", "相談", "面談", "打ち合わせ", "議事録", "ログ"
    ]
    # Check Japanese WEB keywords
    web_keywords = ["天気", "株価", "三菱", "ニュース", "ネット", "検索", "グーグル", "株"]
    
    if any(k in query_lower for k in web_keywords):
        return "WEB"
    elif any(k in query_lower for k in sql_keywords):
        return "SQL"
    elif any(k in query_lower for k in rag_keywords):
        return "RAG"
    return "MODEL"

def match_pronoun(query: str, display_names: list) -> bool:
    """
    Check if any display name is present in the query.
    """
    query_lower = query.lower()
    for name in display_names:
        name_lower = name.lower()
        if len(name_lower) <= 2:
            is_ascii_alnum = name_lower.isalnum() and name_lower.isascii()
            pattern = rf"\b{re.escape(name_lower)}\b" if is_ascii_alnum else re.escape(name_lower)
            if re.search(pattern, query_lower):
                return True
        else:
            if name_lower in query_lower:
                return True
    return False

def is_date_mismatch(query: str, summary_context) -> bool:
    """
    Returns True if a date mentioned in the query differs from the cache slot's date.
    """
    if not summary_context:
        return False
    if isinstance(summary_context, str):
        try:
            summary_context = json.loads(summary_context)
        except Exception:
            return False
    if not isinstance(summary_context, dict):
        return False
    key_attrs = summary_context.get("key_attributes") or {}
    slot_date_str = key_attrs.get("date") # e.g. "2026-05-04"
    if not slot_date_str:
        return False
        
    try:
        dt = datetime.strptime(slot_date_str, "%Y-%m-%d")
        day, month, year = dt.day, dt.month, dt.year
    except Exception:
        try:
            dt = datetime.strptime(slot_date_str, "%d/%m/%Y")
            day, month, year = dt.day, dt.month, dt.year
        except Exception:
            return False
        
    # Extract D/M or D/M/Y or D-M from query
    query_dates = re.findall(r'\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b', query)
    # Also support Japanese date format: X月Y日 or YYYY年X月Y日
    ja_dates = re.findall(r'(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日', query)
    
    # Check query_dates
    for q_day_str, q_month_str, q_year_str in query_dates:
        q_day = int(q_day_str)
        q_month = int(q_month_str)
        if q_day == day and q_month == month:
            if q_year_str:
                q_year = int(q_year_str)
                if q_year < 100:
                    q_year += 2000
                if q_year == year:
                    return False
            else:
                return False
                
    # Check ja_dates
    for q_year_str, q_month_str, q_day_str in ja_dates:
        q_day = int(q_day_str)
        q_month = int(q_month_str)
        if q_day == day and q_month == month:
            if q_year_str:
                q_year = int(q_year_str)
                if q_year == year:
                    return False
            else:
                return False
                
    if not query_dates and not ja_dates:
        return False
        
    return True # Mismatch

def is_gt_mismatch(query: str, topic_key: str) -> bool:
    """
    Returns True if a GT referenced in the query doesn't match the cache slot's topic key.
    """
    if not topic_key:
        return False
    query_gts = re.findall(r'GT_\d+', query, re.IGNORECASE)
    if not query_gts:
        return False
    for gt in query_gts:
        if gt.upper() in topic_key.upper():
            return False
    return True

class LLMManager:
    async def generate_chat_completion(self, messages, response_format=None, max_retries=5):
        raise NotImplementedError

class GroqClientManager(LLMManager):
    def __init__(self):
        keys = os.getenv("GROQ_API_KEYS", "")
        self.api_keys = [k.strip() for k in keys.split(",") if k.strip()]
        self.current_index = 0
        self.model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        
    def get_client(self) -> AsyncGroq:
        if not self.api_keys:
            raise ValueError("No Groq API keys found in environment variables.")
        key = self.api_keys[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.api_keys)
        return AsyncGroq(api_key=key)

    async def generate_chat_completion(self, messages, response_format=None, max_retries=5):
        for attempt in range(max_retries):
            client = self.get_client()
            try:
                kwargs = {
                    "model": self.model,
                    "messages": messages,
                }
                if response_format:
                    kwargs["response_format"] = response_format
                
                completion = await client.chat.completions.create(**kwargs)
                return completion.choices[0].message.content
            except Exception as e:
                if "429" in str(e) or "rate_limit" in str(e).lower():
                    logger.warning(f"Groq API key rate limited (attempt {attempt+1}/{max_retries}), rotating to next key. Error: {e}")
                    continue
                else:
                    logger.error(f"Error calling Groq API: {e}")
                    if attempt == max_retries - 1:
                        raise e
                    await asyncio.sleep(0.5)
        raise RuntimeError("All Groq API keys failed or rate-limited.")

class JavisQwenManager(LLMManager):
    def __init__(self):
        self.api_key = os.getenv("JAVIS_QWEN_API_KEY")
        self.base_url = os.getenv("JAVIS_QWEN_BASE_URL")
        self.model = os.getenv("JAVIS_QWEN_MODEL")
        if not self.api_key or not self.base_url:
            raise ValueError("Javis Qwen API key or Base URL missing in environment variables.")
        
        # Disable keep-alive to prevent hangs on Windows when endpoint closes connection
        timeout_val = float(os.getenv("JAVIS_QWEN_TIMEOUT", "15.0"))
        limits = httpx.Limits(max_keepalive_connections=0, max_connections=20)
        timeout = httpx.Timeout(timeout_val, connect=3.0, read=timeout_val, write=3.0, pool=3.0)
        self.http_client = httpx.AsyncClient(limits=limits, timeout=timeout)
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            http_client=self.http_client
        )

    async def generate_chat_completion(self, messages, response_format=None, max_retries=3):
        timeout_val = float(os.getenv("JAVIS_QWEN_TIMEOUT", "6.0"))
        for attempt in range(max_retries):
            try:
                kwargs = {
                    "model": self.model,
                    "messages": messages,
                }
                if response_format:
                    kwargs["response_format"] = response_format
                
                completion = await self.client.chat.completions.create(**kwargs, timeout=timeout_val)
                content = completion.choices[0].message.content
                if content and ("<think>" in content or "</think>" in content):
                    if "</think>" in content:
                        content = content.split("</think>")[-1].strip()
                    else:
                        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
                return content
            except Exception as e:
                logger.error(f"Error calling Javis Qwen API (attempt {attempt+1}): {e}")
                if attempt == max_retries - 1:
                    raise e
                await asyncio.sleep(0.5)
        raise RuntimeError("Javis Qwen API failed after retries.")

def get_llm_manager() -> LLMManager:
    mode = os.getenv("LLM_MODE", "groq").lower()
    if mode == "javis-qwen":
        logger.info("Initializing LLMManager in 'javis-qwen' mode.")
        return JavisQwenManager()
    else:
        logger.info("Initializing LLMManager in 'groq' mode (default).")
        return GroqClientManager()

class Router:
    def __init__(self, db_pool, llm_manager: LLMManager, embedding_model: SentenceTransformer):
        self.db_pool = db_pool
        self.llm_manager = llm_manager
        self.embedding_model = embedding_model

    async def route(self, session_id: str, query: str) -> dict:
        """
        Routes the user query using the 2-Tier routing process.
        """
        # Get query embedding first (ensures embedding timeout/failures are logged immediately)
        query_emb = await _safe_embed(query, self.embedding_model)
        embedding_failed = (query_emb is None)

        # --- Tier 1: Fast Filter ---
        
        # 1. Heuristic hard switching check
        if SWITCH_KEYWORDS_PATTERN.search(query):
            logger.info("Tier 1: Hard-switching keyword detected. Routing to Tier 2 for full rewrite.")
            return await self._route_tier_2(session_id, query, routing_reason="hard_switch_keyword", embedding_failed=embedding_failed)
            
        # 2. Lightweight Entity Index Lookup
        entities = await self.db_pool.fetch("""
            SELECT e.cache_slot_id, e.entity_id, e.entity_type, e.display_names, c.topic_key, c.last_pipeline, p.summary_context
            FROM session_entity_index e
            JOIN session_context_cache c ON e.cache_slot_id = c.id
            LEFT JOIN session_context_payload p ON c.id = p.cache_id
            WHERE e.session_id = $1
        """, session_id)
        
        matched_slots = []
        for ent in entities:
            if match_pronoun(query, ent['display_names']):
                matched_slots.append(ent)
                
        # Deduplicate matched slots by cache_slot_id
        unique_matches = {}
        for m in matched_slots:
            unique_matches[m['cache_slot_id']] = m
            
        # Unresolved pronoun check: if query has pronouns or is an ellipsis follow-up but they aren't matched in the Entity Index,
        # bypass to Tier 2 to resolve it via chat history.
        has_pronoun = any(re.search(re.escape(p), query.lower()) for p in PRONOUNS)
        is_ellipsis = query.strip().endswith(("は？", "は", "も？", "も"))
        
        # Check for multiple GTs in query (e.g. comparison)
        query_gts = re.findall(r'GT_\d+', query, re.IGNORECASE)
        
        if len(query_gts) > 1:
            logger.info("Tier 1: Multiple GTs detected in query. Bypassing to Tier 2 for comparison/parallel routing.")
            return await self._route_tier_2(session_id, query, routing_reason="multiple_entities", embedding_failed=embedding_failed)

        if (has_pronoun or is_ellipsis) and len(unique_matches) == 0:
            logger.info("Tier 1: Query contains pronoun or ellipsis but no entity matches in DB. Bypassing to Tier 2.")
            return await self._route_tier_2(session_id, query, routing_reason="unresolved_pronoun", embedding_failed=embedding_failed)
            
        if len(unique_matches) == 1:
            matched_ent = list(unique_matches.values())[0]
            
            # Even if we matched one entity in index, if the query mentions a DIFFERENT GT or Date, it's a mismatch
            if is_gt_mismatch(query, matched_ent['topic_key']) or is_date_mismatch(query, matched_ent['summary_context']):
                logger.info("Tier 1: Detected GT or Date mismatch vs matched entity. Forwarding to Tier 2.")
                return await self._route_tier_2(session_id, query, routing_reason="metadata_mismatch", embedding_failed=embedding_failed)

            logger.info(f"Tier 1: Entity lookup matched exactly one entity: {matched_ent['entity_id']} (slot: {matched_ent['topic_key']})")
            
            # Rewrite pronoun in query
            rewritten_query = query
            for pron in PRONOUNS:
                if pron in query:
                    rewritten_query = rewritten_query.replace(pron, matched_ent['entity_id'])
            
            return {
                "is_follow_up": True,
                "relation_type": "same_entity",
                "use_cache": True,
                "needs_retrieval": "none",
                "context_reuse_type": "full_data_reuse",
                "rewritten_query": rewritten_query,
                "target_topic_key": matched_ent['topic_key'],
                "target_pipeline": matched_ent['last_pipeline'],
                "partial_fetch_params": None,
                "routing_tier": "tier_1",
                "routing_method": "heuristics",
                "embedding_failed": embedding_failed
            }
        elif len(unique_matches) > 1:
            logger.info("Tier 1: Multiple entities matched. Bypass to Tier 2 to resolve ambiguity.")
            return await self._route_tier_2(session_id, query, routing_reason="ambiguous_entities", embedding_failed=embedding_failed)

        # 3. Semantic Embedding Distance (pgvector)
        # Check if we have active caches first
        cache_count = await self.db_pool.fetchval(
            "SELECT COUNT(*) FROM session_context_cache WHERE session_id = $1", session_id
        )
        if cache_count == 0:
            logger.info("No active cache slots for this session. Bypass to Tier 2.")
            return await self._route_tier_2(session_id, query, routing_reason="new_session", embedding_failed=embedding_failed)
            
        if embedding_failed:
            logger.warning("Tier 1: Embedding failed. Downgrading to Tier 2.")
            return await self._route_tier_2(session_id, query, routing_reason="embedding_failure", embedding_failed=True)
            
        # Run cosine distance query joining Cold table payload for mismatch checks
        query_emb_str = "[" + ",".join(map(str, query_emb)) + "]"
        closest_slot = await self.db_pool.fetchrow("""
            SELECT c.id, c.topic_key, c.last_pipeline, (c.query_embedding <=> $1::vector) as distance, p.summary_context
            FROM session_context_cache c
            LEFT JOIN session_context_payload p ON c.id = p.cache_id
            WHERE c.session_id = $2 AND c.query_embedding IS NOT NULL
            ORDER BY distance ASC
            LIMIT 1
        """, query_emb_str, session_id)
        
        if closest_slot:
            dist = closest_slot['distance']
            logger.info(f"Tier 1: Closest cache slot is '{closest_slot['topic_key']}' with distance {dist:.4f}")
            
            # Check Metadata mismatches
            # If query mentions a specific date or GT session, but it doesn't match the closest slot, bypass to Tier 2
            query_gts = re.findall(r'GT_\d+', query, re.IGNORECASE)
            if is_gt_mismatch(query, closest_slot['topic_key']) or is_date_mismatch(query, closest_slot['summary_context']) or len(query_gts) > 1:
                logger.info("Tier 1: Detected GT or Date mismatch. Forwarding to Tier 2.")
                return await self._route_tier_2(session_id, query, routing_reason="metadata_mismatch", embedding_failed=embedding_failed)
                
            if dist < 0.22:  # Similarity > 0.78
                logger.info(f"Tier 1: Semantic match hit! Distance {dist:.4f} < 0.22")
                return {
                    "is_follow_up": True,
                    "relation_type": "same_entity",
                    "use_cache": True,
                    "needs_retrieval": "none",
                    "context_reuse_type": "full_data_reuse",
                    "rewritten_query": query,
                    "target_topic_key": closest_slot['topic_key'],
                    "target_pipeline": closest_slot['last_pipeline'],
                    "partial_fetch_params": None,
                    "routing_tier": "tier_1",
                    "routing_method": "embeddings",
                    "embedding_failed": False
                }
            elif dist > 0.55:  # Similarity < 0.45
                logger.info(f"Tier 1: Semantic shift detected! Distance {dist:.4f} > 0.55")
                guessed_pipeline = heuristic_pipeline_guess(query)
                return {
                    "is_follow_up": False,
                    "relation_type": "topic_shift",
                    "use_cache": False,
                    "needs_retrieval": "full",
                    "context_reuse_type": "none",
                    "rewritten_query": query,
                    "target_topic_key": None,
                    "target_pipeline": guessed_pipeline,
                    "partial_fetch_params": None,
                    "routing_tier": "tier_1",
                    "routing_method": "embeddings",
                    "embedding_failed": False
                }
            else:
                logger.info(f"Tier 1: Gray area (distance {dist:.4f}). Forwarding to Tier 2.")
                
        return await self._route_tier_2(session_id, query, routing_reason="gray_area", embedding_failed=embedding_failed)

    async def _route_tier_2(self, session_id: str, query: str, routing_reason: str, embedding_failed: bool = False) -> dict:
        """
        Tier 2: LLM Router & Rewriter (Groq llama-3.3-70b-versatile).
        """
        logger.info(f"Starting Tier 2 routing. Reason: {routing_reason}")
        
        # 1. Fetch Chat History (last 8 messages)
        history_rows = await self.db_pool.fetch("""
            SELECT role, content, rewritten_content
            FROM chat_history
            WHERE session_id = $1
            ORDER BY id ASC
            LIMIT 8
        """, session_id)
        
        history_str = ""
        for r in history_rows:
            role = "User" if r['role'] == 'user' else "Assistant"
            content = r['rewritten_content'] if (r['role'] == 'user' and r['rewritten_content']) else r['content']
            history_str += f"{role}: {content}\n"
            
        # 2. Fetch Active Caches Metadata
        cache_rows = await self.db_pool.fetch("""
            SELECT c.topic_key, c.last_pipeline, c.last_accessed_at, c.refreshed_at, p.summary_context
            FROM session_context_cache c
            LEFT JOIN session_context_payload p ON c.id = p.cache_id
            WHERE c.session_id = $1
            ORDER BY c.last_accessed_at DESC
        """, session_id)
        
        active_caches = []
        for r in cache_rows:
            summary = None
            if r['summary_context']:
                try:
                    summary = json.loads(r['summary_context'])
                except Exception:
                    summary = r['summary_context']
            active_caches.append({
                "topic_key": r['topic_key'],
                "last_pipeline": r['last_pipeline'],
                "last_accessed_at": r['last_accessed_at'].isoformat() if r['last_accessed_at'] else None,
                "refreshed_at": r['refreshed_at'].isoformat() if r['refreshed_at'] else None,
                "summary_context": summary
            })
            
        active_caches_str = json.dumps(active_caches, ensure_ascii=False, indent=2)
        
        # 3. Call LLM Router
        system_prompt = (
            "あなたはプロのAIルーターおよびクエリ書き換えエンジンです。\n"
            "最近のチャット履歴とアクティブキャッシュ（提供されたコンテキスト）に基づいて、クエリを分析してください。\n\n"
            "[チャット履歴]\n"
            f"{history_str if history_str else '(履歴なし)'}\n\n"
            "[アクティブキャッシュ]\n"
            f"{active_caches_str if active_caches else '[]'}\n\n"
            "【最重要ルール】\n"
            "1. **代名詞の解決とクエリの書き換え (rewritten_query)**:\n"
            "   - クエリに「彼」「彼女」「彼ら」「その人」「先ほどの担当者」などの代名詞や指示語が含まれている場合、チャット履歴を参照して、それらを**具体的な名前や名詞（例：中原さん、島田さん）に置き換えた完全なクエリ**を `rewritten_query` に作成してください。\n"
            "   - 特に「彼らは〜」のように複数の人物を指す場合、履歴から該当する全ての人物を特定して書き換えてください。\n"
            "2. **トピックの切り替え (topic_shift)**:\n"
            "   - クエリが既存のキャッシュ（[アクティブキャッシュ]）と異なるトピックである場合、必ず `target_topic_key` を**新しく作成**（例: 'new_topic_123'）し、`needs_retrieval: \"full\"` にしてください。\n"
            "   - **既存のトピックキーを別の種類の情報（例：GT_04の通話にWEB検索の結果を入れる）で上書きしないでください。**\n"
            "3. **Pipeline の厳格な使い分け**:\n"
            "   - **SQL**: 通話時間（duration）、日付（meeting_date）、参加者（participants）、件数、通話の有無など、データベースの**数値や構造化データ**が必要な場合。\n"
            "   - **RAG**: 会話の具体的な内容、発言の詳細、要約、特定の話題（例: 内見(ないけん・物件の内覧)、契約、物件情報、顧客情報、交渉内容など）について何を話したかなど、通話録音やテキストの**読解・要約**が必要な場合。\n"
            "   - **WEB**: データベースにない外部情報（最新の株価、一般ニュース、社外の一般知識など）が必要な場合。\n"
            "   - **MODEL**: 挨拶、日常会話、データベースと関係のない純粋な雑談・相談のみ。\n"
            "   - **重要**: 過去の通話、履歴、内見、または特定の業務データに関する質問は、絶対に SQL または RAG に振り分けてください。これらを MODEL に振り分けてはいけません！\n"
            "3. **キャッシュの再利用**:\n"
            "   - 同一トピックへの継続質問（same_entity等）の場合のみ、既存の `target_topic_key` を正確に使用してください。\n\n"
            "出力形式（JSONのみ）：\n"
            "{\n"
            "  \"is_follow_up\": boolean,\n"
            "  \"relation_type\": \"same_entity\" | \"topic_shift\" | \"clarification\",\n"
            "  \"use_cache\": boolean,\n"
            "  \"needs_retrieval\": \"none\" | \"partial\" | \"full\",\n"
            "  \"rewritten_query\": \"代名詞を補完した完全な日本語クエリ\",\n"
            "  \"target_topic_key\": \"新規または既存のキー\",\n"
            "  \"target_pipeline\": \"SQL\" | \"RAG\" | \"WEB\" | \"MODEL\",\n"
            "  \"partial_fetch_params\": null\n"
            "}"
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]
        
        try:
            response_text = await self.llm_manager.generate_chat_completion(
                messages=messages, response_format={"type": "json_object"}
            )
            result = extract_json(response_text)
            # Ensure all required keys exist with safe defaults
            defaults = {
                "is_follow_up": False,
                "relation_type": "topic_shift",
                "use_cache": False,
                "needs_retrieval": "full",
                "context_reuse_type": "none",
                "rewritten_query": query,
                "target_topic_key": f"default_topic_{int(time.time())}",
                "target_pipeline": "MODEL",
                "partial_fetch_params": None
            }
            for k, v in defaults.items():
                if k not in result:
                    result[k] = v
            
            # Clean and sanitize target_topic_key
            if "target_topic_key" in result and isinstance(result["target_topic_key"], str):
                result["target_topic_key"] = result["target_topic_key"].strip().strip('"').strip("'")
                
            # Synchronize target_topic_key with active caches to prevent case-sensitive mismatches
            if result.get("target_topic_key"):
                target_key = result["target_topic_key"]
                matched_key = None
                for cache in active_caches:
                    if cache["topic_key"].lower() == target_key.lower():
                        matched_key = cache["topic_key"]
                        break
                
                if matched_key:
                    # Use the exact case-sensitive key from the database
                    result["target_topic_key"] = matched_key
                else:
                    # If LLM requested cache reuse for a non-existent key, downgrade to full retrieval
                    if result.get("use_cache"):
                        logger.warning(f"LLM requested cache reuse for key '{target_key}' but it does not exist in active caches. Downgrading to full retrieval.")
                        result["use_cache"] = False
                        if result.get("needs_retrieval") == "none":
                            result["needs_retrieval"] = "full"
            
            # Heuristic Override: If query mentions GT session, never allow MODEL or WEB pipeline
            if any(re.search(r'GT_\d+', q, re.IGNORECASE) for q in [query, result.get("rewritten_query", "")]):
                if result.get("target_pipeline") in ["MODEL", "WEB"]:
                    guessed = heuristic_pipeline_guess(query)
                    result["target_pipeline"] = guessed if guessed in ["SQL", "RAG"] else "RAG"
                    logger.info(f"Router override: GT session detected in query. Forcing target_pipeline to '{result['target_pipeline']}'.")
        except Exception as e:
            logger.error(f"Error calling LLM Router: {e}. Activating fallback routing.")
            query_emb = await _safe_embed(query, self.embedding_model)
            closest_slot = None
            if query_emb is not None:
                try:
                    query_emb_str = "[" + ",".join(map(str, query_emb)) + "]"
                    closest_slot = await self.db_pool.fetchrow("""
                        SELECT topic_key, last_pipeline, (query_embedding <=> $1::vector) as distance
                        FROM session_context_cache
                        WHERE session_id = $2 AND query_embedding IS NOT NULL
                        ORDER BY distance ASC
                        LIMIT 1
                    """, query_emb_str, session_id)
                except Exception as db_err:
                    logger.error(f"Failed to query closest slot for fallback: {db_err}")

            if closest_slot:
                dist = closest_slot['distance']
                logger.info(f"Fallback routing: closest slot is '{closest_slot['topic_key']}' with distance {dist:.4f}")
                if dist < 0.22:
                    result = {
                        "is_follow_up": True,
                        "relation_type": "same_entity",
                        "use_cache": True,
                        "needs_retrieval": "none",
                        "context_reuse_type": "full_data_reuse",
                        "rewritten_query": query,
                        "target_topic_key": closest_slot['topic_key'],
                        "target_pipeline": closest_slot['last_pipeline'],
                        "partial_fetch_params": None,
                        "routing_method": "embeddings"
                    }
                elif dist > 0.55:
                    guessed_pipeline = heuristic_pipeline_guess(query)
                    result = {
                        "is_follow_up": False,
                        "relation_type": "topic_shift",
                        "use_cache": False,
                        "needs_retrieval": "full",
                        "context_reuse_type": "none",
                        "rewritten_query": query,
                        "target_topic_key": f"fallback_{int(time.time())}",
                        "target_pipeline": guessed_pipeline,
                        "partial_fetch_params": None,
                        "routing_method": "embeddings"
                    }
                else:
                    guessed_pipeline = heuristic_pipeline_guess(query)
                    result = {
                        "is_follow_up": False,
                        "relation_type": "topic_shift",
                        "use_cache": False,
                        "needs_retrieval": "full",
                        "context_reuse_type": "none",
                        "rewritten_query": query,
                        "target_topic_key": f"fallback_{int(time.time())}",
                        "target_pipeline": guessed_pipeline,
                        "partial_fetch_params": None,
                        "routing_method": "embeddings"
                    }
            else:
                guessed_pipeline = heuristic_pipeline_guess(query)
                result = {
                    "is_follow_up": False,
                    "relation_type": "topic_shift",
                    "use_cache": False,
                    "needs_retrieval": "full",
                    "context_reuse_type": "none",
                    "rewritten_query": query,
                    "target_topic_key": f"fallback_{int(time.time())}",
                    "target_pipeline": guessed_pipeline,
                    "partial_fetch_params": None,
                    "routing_method": "fallback"
                }
            
            result["routing_tier"] = "tier_2"
            # Do not overwrite routing_method if it was set by fallback
            if "routing_method" not in result:
                result["routing_method"] = "llm_router"
            result["embedding_failed"] = embedding_failed
            return result

        result["routing_tier"] = "tier_2"
        result["routing_method"] = "llm_router"
        result["embedding_failed"] = embedding_failed
        
        # Check TTL override for WEB cache
        if result.get("use_cache") and result.get("target_topic_key"):
            target_slot = next((c for c in active_caches if c["topic_key"] == result["target_topic_key"]), None)
            if target_slot and target_slot["last_pipeline"] == "WEB":
                refreshed_at_str = target_slot.get("refreshed_at")
                if refreshed_at_str:
                    refreshed_at = datetime.fromisoformat(refreshed_at_str.replace("Z", "+00:00"))
                    now = datetime.now(timezone.utc)
                    age_seconds = (now - refreshed_at).total_seconds()
                    if age_seconds > 3600:
                        logger.info(f"WEB cache slot '{result['target_topic_key']}' expired (age {age_seconds:.1f}s > 3600s). Forcing full retrieval.")
                        result["use_cache"] = False
                        result["needs_retrieval"] = "full"
                        result["context_reuse_type"] = "none"
                        
        return result
