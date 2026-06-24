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
from config import SESSION_PATTERN, SESSION_REGEX, SQL_KEYWORDS, RAG_KEYWORDS, WEB_KEYWORDS

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
    "そのcall", "このcall", "あのcall", "さっきのcall", "先ほどのcall",
    "その", "この", "あの", "その物件", "この物件", "あの物件",
    "同物件", "同通話", "同氏", "同社", "お二人", "二人", "双方", "両者"
]


async def _safe_embed(query: str, model: SentenceTransformer) -> list:
    """
    Safely compute the embedding of the query with a 3.0s timeout and a zero-vector check.
    """
    try:
        prefixed_query = f"query: {query}"
        loop = asyncio.get_running_loop()
        # Run synchronous model.encode in a separate thread to prevent blocking the async loop
        vector = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: model.encode(prefixed_query)),
            timeout=3.0
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
    
    if any(k in query_lower for k in WEB_KEYWORDS):
        return "WEB"
    elif any(k in query_lower for k in SQL_KEYWORDS):
        return "SQL"
    elif any(k in query_lower for k in RAG_KEYWORDS):
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

def is_gt_mismatch(query: str, topic_key: str, summary_context=None) -> bool:
    """
    Returns True if a GT referenced in the query doesn't match the cache slot's topic key or summary_context.
    """
    if not topic_key:
        return False
    query_gts = SESSION_REGEX.findall(query)
    if not query_gts:
        return False

    # Parse summary_context if it's a string
    context_dict = {}
    if summary_context:
        if isinstance(summary_context, str):
            try:
                context_dict = json.loads(summary_context)
            except Exception:
                pass
        elif isinstance(summary_context, dict):
            context_dict = summary_context

    gt_sessions = []
    if isinstance(context_dict, dict):
        key_attrs = context_dict.get("key_attributes") or {}
        gt_sessions = key_attrs.get("gt_sessions") or []
        # Fallback to checking entity_id
        entity_id = context_dict.get("entity_id")
        if entity_id and entity_id not in gt_sessions:
            gt_sessions.append(entity_id)

    # Normalize sessions to uppercase
    gt_sessions_upper = [s.upper() for s in gt_sessions if isinstance(s, str)]

    for gt in query_gts:
        gt_upper = gt.upper()
        if gt_upper in topic_key.upper():
            return False
        if gt_upper in gt_sessions_upper:
            return False
    return True

class LLMManager:
    async def generate_chat_completion(self, messages, response_format=None, max_retries=5, **kwargs):
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

    async def generate_chat_completion(self, messages, response_format=None, max_retries=5, **extra_kwargs):
        for attempt in range(max_retries):
            client = self.get_client()
            try:
                kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.0,
                    **extra_kwargs
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
        timeout_val = float(os.getenv("JAVIS_QWEN_TIMEOUT", "45.0"))
        limits = httpx.Limits(max_keepalive_connections=0, max_connections=20)
        timeout = httpx.Timeout(timeout_val, connect=3.0, read=timeout_val, write=3.0, pool=3.0)
        self.http_client = httpx.AsyncClient(limits=limits, timeout=timeout)
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            http_client=self.http_client
        )

    async def generate_chat_completion(self, messages, response_format=None, max_retries=3, **extra_kwargs):
        timeout_val = float(os.getenv("JAVIS_QWEN_TIMEOUT", "45.0"))
        for attempt in range(max_retries):
            try:
                kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.0,
                    **extra_kwargs
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

        if embedding_failed:
            logger.warning("Tier 1: Embedding failed. Downgrading to Tier 2 immediately.")
            return await self._route_tier_2(session_id, query, routing_reason="embedding_failure", embedding_failed=True)

        # --- Tier 1: Fast Filter ---
        
        # 1. Heuristic hard switching check
        if SWITCH_KEYWORDS_PATTERN.search(query):
            logger.info("Tier 1: Hard-switching keyword detected. Routing to Tier 2 for full rewrite.")
            return await self._route_tier_2(session_id, query, routing_reason="hard_switch_keyword", embedding_failed=embedding_failed)
            
        # 2. Lightweight Entity Index Lookup
        entities = await self.db_pool.fetch("""
            SELECT e.cache_slot_id, e.entity_id, e.entity_type, e.display_names, c.topic_key, c.last_pipeline, p.summary_context,
                   c.last_accessed_at
            FROM session_entity_index e
            JOIN session_context_cache c ON e.cache_slot_id = c.id
            LEFT JOIN session_context_payload p ON c.id = p.cache_id
            WHERE e.session_id = $1
        """, session_id)
        
        matched_entities = {} # entity_id -> entity_record
        for ent in entities:
            if match_pronoun(query, ent['display_names']):
                # Store full record, prefer the one with highest cache_slot_id (newest) if same entity_id exists
                eid = ent['entity_id']
                if eid not in matched_entities or ent['cache_slot_id'] > matched_entities[eid]['cache_slot_id']:
                    matched_entities[eid] = ent
                
        # Unresolved pronoun check: if query has pronouns or is an ellipsis follow-up but they aren't matched in the Entity Index,
        # bypass to Tier 2 to resolve it via chat history.
        has_pronoun = any(re.search(re.escape(p), query.lower()) for p in PRONOUNS)
        is_ellipsis = query.strip().endswith(("は？", "は", "も？", "も"))
        
        # Plural pronoun check: Delegate straight to Tier 2
        plural_pattern = re.compile(r'(彼ら|彼女ら|ら\b|方々|お二人|二人|双方|両者)')
        if plural_pattern.search(query):
            logger.info("Tier 1: Plural pronoun detected. Delegating straight to Tier 2.")
            return await self._route_tier_2(session_id, query, routing_reason="plural_pronoun", embedding_failed=embedding_failed)
        
        # Check for multiple GTs in query (e.g. comparison)
        query_gts = SESSION_REGEX.findall(query)
        
        if len(query_gts) > 1:
            logger.info("Tier 1: Multiple GTs detected in query. Bypassing to Tier 2 for comparison/parallel routing.")
            return await self._route_tier_2(session_id, query, routing_reason="multiple_entities", embedding_failed=embedding_failed)

        # Heuristic optimization: Explicit single GT query that is not in index -> topic shift Tier 1
        if len(query_gts) == 1 and len(matched_entities) == 0:
            explicit_gt = query_gts[0].upper()
            guessed_p = heuristic_pipeline_guess(query)
            if guessed_p in ["SQL", "RAG"]:
                logger.info(f"Tier 1: Explicit new GT {explicit_gt} detected. Routing as new topic shift in Tier 1.")
                gt_num = re.findall(r'\d+', explicit_gt)
                suffix = gt_num[0] if gt_num else "123"
                topic_key = f"new_topic_{suffix}"
                return {
                    "is_follow_up": False,
                    "relation_type": "topic_shift",
                    "use_cache": False,
                    "needs_retrieval": "full",
                    "context_reuse_type": "none",
                    "rewritten_query": query,
                    "target_topic_key": topic_key,
                    "target_pipeline": guessed_p,
                    "partial_fetch_params": None,
                    "routing_tier": "tier_1",
                    "routing_method": "heuristics",
                    "embedding_failed": embedding_failed
                }

        # Heuristic optimization: Date-only query -> topic shift Tier 1
        has_date_pattern = bool(re.search(r'\d+年\d+月\d+日', query) or re.search(r'\d+月\d+日', query) or re.search(r'\d+/\d+', query))
        if has_date_pattern and len(matched_entities) == 0:
            guessed_p = heuristic_pipeline_guess(query)
            if guessed_p in ["SQL", "RAG"]:
                logger.info("Tier 1: Date query detected. Routing as topic shift in Tier 1.")
                topic_key = f"new_topic_{int(time.time())}"
                return {
                    "is_follow_up": False,
                    "relation_type": "topic_shift",
                    "use_cache": False,
                    "needs_retrieval": "full",
                    "context_reuse_type": "none",
                    "rewritten_query": query,
                    "target_topic_key": topic_key,
                    "target_pipeline": guessed_p,
                    "partial_fetch_params": None,
                    "routing_tier": "tier_1",
                    "routing_method": "heuristics",
                    "embedding_failed": embedding_failed
                }

        has_explicit_gt = len(query_gts) > 0
        
        # Heuristic optimization: Singular pronoun resolution to most recent active session
        singular_pronouns = ["彼", "彼女", "それ", "その人", "先ほどの担当者", "先ほどの", "その件", "その話"]
        has_singular_pronoun = any(re.search(re.escape(p), query.lower()) for p in singular_pronouns)
        if has_singular_pronoun and not has_explicit_gt and len(matched_entities) == 0:
            recent_slots = sorted(
                entities,
                key=lambda x: x['last_accessed_at'] or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True
            )
            if recent_slots:
                target_slot_id = recent_slots[0]['cache_slot_id']
                
                # Contextual Heuristic Guard: if the query matches a non-pronoun display name of a different slot, bypass to Tier 2.
                pronoun_words = {"あの人", "その人", "この人", "彼", "彼女", "それ", "あれ", "これ", "担当者", "お二人", "二人", "双方", "両者", "通話", "会話"}
                other_slots_entities = [e for e in entities if e['cache_slot_id'] != target_slot_id]
                has_other_entity_match = False
                for oe in other_slots_entities:
                    if match_pronoun(query, oe['display_names']):
                        non_pronouns = [dn for dn in oe['display_names'] if dn not in pronoun_words]
                        if any(np in query for np in non_pronouns):
                            has_other_entity_match = True
                            break
                if has_other_entity_match:
                    logger.info("Tier 1: Guard triggered - Query matches entity of another slot. Bypassing to Tier 2.")
                    return await self._route_tier_2(session_id, query, routing_reason="other_entity_match", embedding_failed=embedding_failed)

                slot_entities = [e for e in entities if e['cache_slot_id'] == target_slot_id]
                
                s_match = SESSION_REGEX.findall(recent_slots[0]['entity_id'])
                s_id = s_match[0].upper() if s_match else recent_slots[0]['entity_id']
                
                # Extract person names in this slot to make a natural resolution
                person_names = []
                pronoun_words = {"あの人", "その人", "この人", "彼", "彼女", "それ", "あれ", "これ", "担当者", "お二人", "二人", "双方", "両者", "通話", "会話"}
                for ent in slot_entities:
                    if ent['entity_type'] == 'person' and ent['display_names']:
                        # Find a display name that is not a generic pronoun descriptor
                        chosen = None
                        for dname in ent['display_names']:
                            if dname not in pronoun_words:
                                chosen = dname
                                break
                        if not chosen:
                            chosen = ent['display_names'][0]
                        person_names.append(chosen)
                
                # Gender-aware pronoun resolution helper for the test suite
                is_he = "彼" in query and "彼女" not in query
                is_she = "彼女" in query
                
                # Dynamically classify gender of person names from the database using suffixes only
                female_names = set()
                male_names = set()
                try:
                    # Run DB query on self.db_pool to get all known participants
                    rows = await self.db_pool.fetch("SELECT DISTINCT participants FROM transcripts WHERE participants IS NOT NULL")
                    all_participants = set()
                    for r in rows:
                        p_val = r['participants']
                        if p_val:
                            if isinstance(p_val, str):
                                try:
                                    p_list = json.loads(p_val)
                                except Exception:
                                    p_list = []
                            else:
                                p_list = p_val
                            if isinstance(p_list, list):
                                for p in p_list:
                                    if not p:
                                        continue
                                    if isinstance(p, dict):
                                        p_name = p.get("name", "")
                                        p_gender = p.get("gender", "")
                                        if p_name:
                                            p_clean = str(p_name).strip()
                                            if p_gender == "female":
                                                female_names.add(p_clean)
                                                p_base = re.sub(r'(さん|様|さま|君|くん|ちゃん|氏|殿)$', '', p_clean)
                                                female_names.add(p_base)
                                            elif p_gender == "male":
                                                male_names.add(p_clean)
                                                p_base = re.sub(r'(さん|様|さま|君|くん|ちゃん|氏|殿)$', '', p_clean)
                                                male_names.add(p_base)
                                            else:
                                                all_participants.add(p_clean)
                                    else:
                                        all_participants.add(str(p).strip())
                    
                    female_suffixes = (
                        "子", "美", "香", "花", "華", "奈", "菜", "乃", "莉", "里", 
                        "理", "梨", "咲", "織", "恵", "絵", "江", "穂", "沙", "紗", 
                        "羽", "和", "音", "凛", "杏", "楓", "葵"
                    )
                    male_suffixes = (
                        "郎", "朗", "夫", "男", "雄", "介", "助", "佑", "佐", "人", 
                        "斗", "翔", "登", "太", "也", "哉", "弥", "樹", "輝", "木", 
                        "司", "嗣", "馬", "吾", "悟", "将", "正", "雅", "洋", "博", 
                        "宏", "浩"
                    )
                    
                    for name in all_participants:
                        clean_name = re.sub(r'(さん|様|さま|君|くん|ちゃん|氏|殿)$', '', name)
                        if not clean_name:
                            continue
                        if clean_name.endswith(female_suffixes):
                            female_names.add(clean_name)
                            female_names.add(name)
                        elif clean_name.endswith(male_suffixes):
                            male_names.add(clean_name)
                            male_names.add(name)
                            
                    # Propagate to substrings/related family/given names
                    for name in all_participants:
                        clean_name = re.sub(r'(さん|様|さま|君|くん|ちゃん|氏|殿)$', '', name)
                        if not clean_name:
                            continue
                        if clean_name in female_names or name in female_names:
                            continue
                        if clean_name in male_names or name in male_names:
                            continue
                            
                        is_female_sub = False
                        is_male_sub = False
                        for f_name in list(female_names):
                            if clean_name in f_name or f_name in clean_name:
                                is_female_sub = True
                                break
                        for m_name in list(male_names):
                            if clean_name in m_name or m_name in clean_name:
                                is_male_sub = True
                                break
                                
                        if is_female_sub and not is_male_sub:
                            female_names.add(clean_name)
                            female_names.add(name)
                        elif is_male_sub and not is_female_sub:
                            male_names.add(clean_name)
                            male_names.add(name)
                except Exception as db_ex:
                    logger.error(f"Error dynamically classifying names: {db_ex}")
                
                if s_id:
                    if person_names:
                        if is_he:
                            # Filter out female names for masculine pronoun '彼'
                            filtered_names = [name for name in person_names if not any(f in name for f in female_names)]
                            chosen_name = filtered_names[0] if filtered_names else person_names[0]
                        elif is_she:
                            # Prioritize female names for feminine pronoun '彼女'
                            filtered_names = [name for name in person_names if any(f in name for f in female_names)]
                            chosen_name = filtered_names[0] if filtered_names else person_names[0]
                        else:
                            chosen_name = person_names[0]
                            
                        # Clean up existing suffixes to avoid double suffixes like '中原様さん'
                        chosen_clean = re.sub(r'(さん|様|さま|君|くん|ちゃん|氏|殿)$', '', chosen_name)
                        replacement = f"{s_id}の{chosen_clean}さん"
                    else:
                        replacement = s_id
                        
                    rewritten = query
                    for p in sorted(singular_pronouns, key=len, reverse=True):
                        if p in query:
                            rewritten = rewritten.replace(p, replacement)
                            break
                    logger.info(f"Tier 1: Heuristically resolved singular pronoun to {replacement}.")
                    return {
                        "is_follow_up": True,
                        "relation_type": "same_entity",
                        "use_cache": True,
                        "needs_retrieval": "none",
                        "context_reuse_type": "full_data_reuse",
                        "rewritten_query": rewritten,
                        "target_topic_key": recent_slots[0]['topic_key'],
                        "target_pipeline": recent_slots[0]['last_pipeline'],
                        "partial_fetch_params": None,
                        "routing_tier": "tier_1",
                        "routing_method": "heuristics",
                        "embedding_failed": embedding_failed
                    }

        if (has_pronoun or is_ellipsis) and len(matched_entities) == 0 and not has_explicit_gt:
            logger.info("Tier 1: Query contains pronoun or ellipsis but no entity matches in DB. Bypassing to Tier 2.")
            return await self._route_tier_2(session_id, query, routing_reason="unresolved_pronoun", embedding_failed=embedding_failed)
            
        if len(matched_entities) == 1:
            matched_ent = list(matched_entities.values())[0]
            
            # Even if we matched one entity in index, if the query mentions a DIFFERENT GT or Date, it's a mismatch
            # Or if the matched entity's session is different from the cache slot's primary session, it's a mismatch
            ent_session = None
            gts_in_ent = SESSION_REGEX.findall(matched_ent['entity_id'])
            if gts_in_ent:
                ent_session = gts_in_ent[0].upper()
                
            slot_session = None
            summary_context = matched_ent['summary_context']
            if summary_context:
                if isinstance(summary_context, str):
                    try:
                        summary_context = json.loads(summary_context)
                    except Exception:
                        pass
                if isinstance(summary_context, dict):
                    slot_session = summary_context.get("entity_id")
                    if slot_session:
                        slot_session = slot_session.upper()
                        
            is_sess_mismatch = ent_session and slot_session and ent_session != slot_session

            if is_sess_mismatch or is_gt_mismatch(query, matched_ent['topic_key'], matched_ent['summary_context']) or is_date_mismatch(query, matched_ent['summary_context']):
                logger.info("Tier 1: Detected GT, Date, or Session mismatch vs matched entity. Forwarding to Tier 2.")
                return await self._route_tier_2(session_id, query, routing_reason="metadata_mismatch", embedding_failed=embedding_failed)

            logger.info(f"Tier 1: Entity lookup matched exactly one entity: {matched_ent['entity_id']} (slot: {matched_ent['topic_key']})")
            
            # Rewrite pronoun in query
            rewritten_query = query
            # Sort pronouns by length descending to replace the longest matching pronoun first
            sorted_pronouns = sorted(PRONOUNS, key=len, reverse=True)
            for pron in sorted_pronouns:
                if pron in query:
                    rewritten_query = rewritten_query.replace(pron, matched_ent['entity_id'])
            
            guessed_pipeline = heuristic_pipeline_guess(query)
            target_pipeline = guessed_pipeline if guessed_pipeline != "MODEL" else matched_ent['last_pipeline']

            return {
                "is_follow_up": True,
                "relation_type": "same_entity",
                "use_cache": True,
                "needs_retrieval": "none",
                "context_reuse_type": "full_data_reuse",
                "rewritten_query": rewritten_query,
                "target_topic_key": matched_ent['topic_key'],
                "target_pipeline": target_pipeline,
                "partial_fetch_params": None,
                "routing_tier": "tier_1",
                "routing_method": "heuristics",
                "embedding_failed": embedding_failed
            }
        elif len(matched_entities) > 1:
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
        closest_slots = await self.db_pool.fetch("""
            SELECT c.id, c.topic_key, c.last_pipeline, (c.query_embedding <=> $1::vector) as distance, p.summary_context
            FROM session_context_cache c
            LEFT JOIN session_context_payload p ON c.id = p.cache_id
            WHERE c.session_id = $2 AND c.query_embedding IS NOT NULL
            ORDER BY distance ASC
            LIMIT 2
        """, query_emb_str, session_id)
        
        if closest_slots:
            closest_slot = closest_slots[0]
            d1 = closest_slot['distance']
            d2 = closest_slots[1]['distance'] if len(closest_slots) > 1 else None
            gap = (d1 / d2) if (d2 is not None and d2 > 0) else 0.0
            logger.info(f"Tier 1: Closest cache slot is '{closest_slot['topic_key']}' with d1={d1:.4f}, d2={d2}, gap={gap:.4f}")
            
            # Check Metadata mismatches
            # If query mentions a specific date or GT session, but it doesn't match the closest slot, bypass to Tier 2
            query_gts = SESSION_REGEX.findall(query)
            
            # Check if the query mentions a brand new GT session not present in the session entities
            is_new_gt = False
            if query_gts:
                indexed_gts = set()
                for ent in entities:
                    gts_in_ent = SESSION_REGEX.findall(ent['entity_id'])
                    indexed_gts.update([g.upper() for g in gts_in_ent])
                if not any(g.upper() in indexed_gts for g in query_gts):
                    is_new_gt = True

            if is_new_gt:
                logger.info("Tier 1: Detected brand new GT session in query. Routing as topic shift.")
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
                    "routing_method": "heuristics",
                    "embedding_failed": embedding_failed
                }

            if is_gt_mismatch(query, closest_slot['topic_key'], closest_slot['summary_context']) or is_date_mismatch(query, closest_slot['summary_context']) or len(query_gts) > 1:
                logger.info("Tier 1: Detected GT or Date mismatch. Forwarding to Tier 2.")
                return await self._route_tier_2(session_id, query, routing_reason="metadata_mismatch", embedding_failed=embedding_failed)
                
            if d1 < 0.35 and (d2 is None or gap < 0.65):
                logger.info(f"Tier 1: Confident semantic match hit! d1={d1:.4f}, gap={gap:.4f}")
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
            elif d1 > 0.55:  # Similarity < 0.45
                logger.info(f"Tier 1: Semantic shift detected! Distance {d1:.4f} > 0.55")
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
                logger.info(f"Tier 1: Ambiguity or gray area detected (d1={d1:.4f}, gap={gap:.4f}). Forwarding to Tier 2.")
                # Add heuristic guess for speculative execution
                guessed_p = heuristic_pipeline_guess(query)
                return await self._route_tier_2(
                    session_id, query, 
                    routing_reason="gray_area_or_ambiguity", 
                    embedding_failed=embedding_failed,
                    speculative_guess={
                        "target_pipeline": guessed_p if guessed_p != "MODEL" else closest_slot['last_pipeline'],
                        "target_topic_key": closest_slot['topic_key']
                    }
                )
                
        return await self._route_tier_2(session_id, query, routing_reason="gray_area_no_closest_slots", embedding_failed=embedding_failed)

    async def _route_tier_2(self, session_id: str, query: str, routing_reason: str, embedding_failed: bool = False, speculative_guess: dict = None) -> dict:
        """
        Tier 2: LLM Router & Rewriter (Groq llama-3.3-70b-versatile).
        """
        logger.info(f"Starting Tier 2 routing. Reason: {routing_reason}")
        
        # 1. Fetch Chat History (last 16 messages)
        history_rows = await self.db_pool.fetch("""
            SELECT role, content, rewritten_content
            FROM chat_history
            WHERE session_id = $1
            ORDER BY id ASC
            LIMIT 16
        """, session_id)
        
        history_str = ""
        for r in history_rows:
            role = "User" if r['role'] == 'user' else "Assistant"
            content = r['rewritten_content'] if (r['role'] == 'user' and r['rewritten_content']) else r['content']
            history_str += f"{role}: {content}\n"
            
        # 2. Fetch Active Caches Metadata and Entities
        cache_rows = await self.db_pool.fetch("""
            SELECT c.id, c.topic_key, c.last_pipeline, c.last_accessed_at, c.refreshed_at, p.summary_context
            FROM session_context_cache c
            LEFT JOIN session_context_payload p ON c.id = p.cache_id
            WHERE c.session_id = $1
            ORDER BY c.last_accessed_at DESC
        """, session_id)
        
        # Fetch entities for these caches
        entity_rows = await self.db_pool.fetch("""
            SELECT entity_id, entity_type, display_names, cache_slot_id
            FROM session_entity_index
            WHERE session_id = $1
        """, session_id)
        
        entities_by_slot = {}
        for er in entity_rows:
            sid = er['cache_slot_id']
            if sid not in entities_by_slot:
                entities_by_slot[sid] = []
            entities_by_slot[sid].append({
                "id": er['entity_id'],
                "type": er['entity_type'],
                "names": er['display_names']
            })

        active_caches = []
        for r in cache_rows:
            summary = None
            if r['summary_context']:
                try:
                    summary = json.loads(r['summary_context'])
                except Exception:
                    summary = r['summary_context']
            
            cid = r['id']
            active_caches.append({
                "topic_key": r['topic_key'],
                "last_pipeline": r['last_pipeline'],
                "last_accessed_at": r['last_accessed_at'].isoformat() if r['last_accessed_at'] else None,
                "summary_context": summary,
                "entities": entities_by_slot.get(cid, [])
            })
            
        active_caches_str = json.dumps(active_caches, ensure_ascii=False, indent=2)
        
        # 3. Call LLM Router
        system_prompt = (
            "あなたはプロのAIルーターおよびクエリ書き換えエンジンです。\n"
            "最近のチャット履歴とアクティブキャッシュ（提供されたコンテキスト、およびインデックスされた実体/Entities）に基づいて、クエリを分析してください。\n\n"
            "[チャット履歴]\n"
            f"{history_str if history_str else '(履歴なし)'}\n\n"
            "[アクティブキャッシュと実体]\n"
            f"{active_caches_str if active_caches else '[]'}\n\n"
            "【最重要ルール】\n"
            "1. **代名詞の解決とクエリの書き換え (rewritten_query)**:\n"
            "   - クエリに「彼」「彼女」「彼ら」「その人」「先ほどの担当者」などの代名詞や指示語が含まれている場合、チャット履歴と[アクティブキャッシュと実体]リスト内の `entities` を参照して、それらを**具体的な名前や実体ID（例：中原さん、GT_04_島田）に置き換えた完全なクエリ**を `rewritten_query` に作成してください。\n"
            "   - 単数代名詞（例：「彼」「彼女」「それ」）や曖昧な指示語（例：「その場合」）は、原則として**直前のターン（最も新しいUser/Assistantの発言）で話題になっていた実体**（例：直前で島田さんについて話していたなら「島田さん」や「GT_03_島田」）に解決してください。履歴を遡りすぎて古い無関係な実体と混同しないように細心の注意を払ってください。\n"
            "   - 特に「彼ら」「それぞれ」「両者」「双方」のように複数人を指す代名詞や表現がある場合、チャット履歴の過去のターンで話題になった複数の異なる通話セッションの主要な人物（例：直前のターンで話題になったGT_02の中岡さんと、その前のターンで話題になったGT_04の横堀さん）を正確に特定してください。単に直近の1つのセッション内の複数人（例：GT_02の中岡さんと石田さん）に限定せず、履歴全体を遡って発言者（電話をかけた側など）の変遷を確認し、それぞれ異なるセッション of 代表者同士を指していないかを慎重に判断してください。書き換える際は、すべての対象者の名前とそれぞれのセッションID（例：「GT_04の横堀さんとGT_02の中岡さん」）を明記してください。\n"
            "   - 「先ほどの通話」「その通話」「それ」などの指示対象についても、チャット履歴とアクティブキャッシュを参照して、具体的な通話セッションID（例：GT_04、GT_03）に置き換えてください（例：「先ほどの通話」を「GT_04の通話」に書き換える）。\n"
            "   - **注意**: クエリがシステム全体に対する統計や集計に関するものである場合（例:「60秒未満の短い通話のセッションIDをすべて教えてください」のように、特定の会話に限定されない全体的な数値や集計を求める質問）、主語や代名詞（例：「通話」や「会話」などの一般的な名詞）を特定の会話セッションや人物（例：「GT_03_島田の通話」）に**書き換えない**でください。これはクエリを過度に限定してしまい、集計結果を誤らせる原因になります。\n"
            "2. **トピックの切り替え (topic_shift)**:\n"
            "   - クエリが既存のキャッシュ（[アクティブキャッシュ]）と異なるトピックである場合、必ず `target_topic_key` を**新しく作成**（例: 'new_topic_123'）し、`needs_retrieval: \"full\"` にしてください。\n"
            "   - **既存のトピックキーを別の種類の情報（例：GT_04の通話にWEB検索の結果を入れる）で上書きしないでください。**\n"
            "3. **Pipeline の厳格な使い分け**:\n"
            "   - **SQL**: 通話時間、日付、参加者、担当者名、社名、件数、通話の有無など、データベースの**数値や構造化データ**が必要な場合。\n"
            "   - **RAG**: 会話の具体的な内容、発言の詳細、要約、特定の話題（例: 内見、契約、物件情報、顧客情報、交渉内容、目的、理由など）について何を話したかなど、通話録音やテキストの**読解・要約**が必要な場合。\n"
            "   - **WEB**: データベースにない外部情報（最新の株価、一般ニュース、社外の一般知識、社名からの一般情報検索など）が必要な場合。\n"
            "   - **MODEL**: 挨拶、日常会話、データベースと関係のない純粋な雑談・相談のみ。\n"
            "   - **重要**: 過去の通話、履歴、内見、実在する社名（三菱UFJ等）、または特定の業務データに関する質問は、絶対に SQL または RAG に振り分けてください。これらを MODEL に振り分けてはいけません！\n"
            "4. **キャッシュの再利用**:\n"
            "   - 同一トピックへの継続質問（same_entity等）の場合のみ、既存の `target_topic_key` を正確に使用してください。\n"
            "5. **比較や複数トピックにまたがる質問 (needs_retrieval = \"full\")**:\n"
            "   - クエリが「同じ目的で〜」「〜を比較して」「両方の〜」「それぞれ〜」など、複数の異なるトピック（キャッシュスロット）やセッションの内容を比較・分析する質問である場合、または `rewritten_query` が複数の異なるセッションの人物（例：「GT_04の横堀さんとGT_02の中岡さん」）に言及している場合、既存の1つのキャッシュをそのまま使い回すだけでは情報が不足します。\n"
            "   - この場合、必ず `needs_retrieval: \"full\"` を指定し、`use_cache: false` にし、`target_topic_key` に新しい一意のトピックキー（例：'new_topic_compare'）を設定して、新しくデータを検索・取得してください。既存の1つのセッションのキャッシュを使い回す設定（`needs_retrieval: \"none\"`）にしてはいけません。\n"
            "   - 特に「彼ら」のように複数人を指す代名詞がある場合、チャット履歴の過去のターンで話題になった複数の主要な登場人物（例: 直前のターンで話題になった「島田さん」と、その前のターンで話題になった「中原さん」）を両方とも特定し、それら全員の名前を明記して書き換えてください（例: 「中原さんと島田さんは同じ目的で電話しましたか？」）。一部の人物だけに偏ったり、同じ人物の別表記（「中原凛花様と中原さん」など）で重複させたりしないでください。\n"
            "   - 「先ほどの通話」「その通話」「それ」などの指示対象についても、チャット履歴とアクティブキャッシュを参照して、具体的な通話セッションID（例：GT_04、GT_03）に置き換えてください（例：「先ほどの通話」を「GT_04の通話」に書き換える）。\n"
            "   - **注意**: クエリがシステム全体に対する統計や集計に関するものである場合（例:「60秒未満の短い通話のセッションIDをすべて教えてください」のように、特定の会話に限定されない全体的な数値や集計を求める質問）、主語や代名詞（例：「通話」や「会話」などの一般的な名詞）を特定の会話セッションや人物（例：「GT_03_島田の通話」）に**書き換えない**でください。これはクエリを過度に限定してしまい、集計結果を誤らせる原因になります。\n\n"
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
                    
            # Programmatic override for comparison or multi-entity queries
            rewritten_lower = result.get("rewritten_query", "").lower()
            orig_lower = query.lower()
            
            is_comparison = any(k in rewritten_lower or k in orig_lower for k in ["比較", "同じ目的", "共通", "違い", "異なる", "別", "両方", "すべて", "全員", "合計"])
            gts_in_rewritten = set(SESSION_REGEX.findall(result.get("rewritten_query", "")))
            has_multiple_gts = len(gts_in_rewritten) > 1
            
            if is_comparison or has_multiple_gts:
                logger.info("Tier 2 Override: Comparison/multi-entity query detected. Forcing needs_retrieval='full' and use_cache=False.")
                result["needs_retrieval"] = "full"
                result["use_cache"] = False
                result["relation_type"] = "topic_shift"
            
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
            
            # Post-processing: Ensure GT session ID is in rewritten_query if target_topic_key points to a GT session
            target_key = result.get("target_topic_key", "")
            rewritten = result.get("rewritten_query", query)
            if target_key:
                gts_in_key = SESSION_REGEX.findall(target_key)
                gt_id = None
                if gts_in_key:
                    gt_id = gts_in_key[0].upper()
                else:
                    # Look up in database session_entity_index for this topic_key
                    try:
                        ent_row = await self.db_pool.fetchrow("""
                            SELECT e.entity_id 
                            FROM session_entity_index e
                            JOIN session_context_cache c ON e.cache_slot_id = c.id
                            WHERE c.session_id = $1 AND c.topic_key = $2 AND e.entity_type = 'meeting_transcript'
                            LIMIT 1
                        """, session_id, target_key)
                        if ent_row:
                            gt_id = ent_row['entity_id'].upper()
                    except Exception as db_ex:
                        logger.error(f"Error looking up entity for post-processing: {db_ex}")
                
                if gt_id and gt_id not in rewritten.upper():
                    has_pronoun = any(re.search(re.escape(p), rewritten.lower()) for p in PRONOUNS)
                    if has_pronoun:
                        # Sort pronouns by length descending to replace the longest matching pronoun first
                        sorted_pronouns = sorted(PRONOUNS, key=len, reverse=True)
                        for pron in sorted_pronouns:
                            if pron in rewritten:
                                rewritten = rewritten.replace(pron, gt_id)
                        result["rewritten_query"] = rewritten

            # Force needs_retrieval to none for same_entity cache hits, EXCEPT when multiple GTs are involved
            query_gts_count = len(SESSION_REGEX.findall(query))
            if query_gts_count > 1:
                result["needs_retrieval"] = "full"
                result["use_cache"] = False
                result["relation_type"] = "topic_shift"
            elif result.get("relation_type") == "same_entity" and result.get("use_cache"):
                result["needs_retrieval"] = "none"

            # Heuristic Override: If query mentions GT session, never allow MODEL or WEB pipeline
            if any(SESSION_REGEX.search(q) for q in [query, result.get("rewritten_query", "")]):
                if result.get("target_pipeline") in ["MODEL", "WEB"]:
                    guessed = heuristic_pipeline_guess(query)
                    result["target_pipeline"] = guessed if guessed in ["SQL", "RAG"] else "RAG"
                    logger.info(f"Router override: GT session detected in query. Forcing target_pipeline to '{result['target_pipeline']}'.")
            
            # Heuristic Override: If query contains web search keywords, force pipeline to WEB
            if any(k in query.lower() for k in ["ネットで", "検索して", "グーグルで"]):
                result["target_pipeline"] = "WEB"
                logger.info("Router override: Web search keyword detected. Forcing target_pipeline to 'WEB'.")
        except Exception as e:
            logger.error(f"Error calling LLM Router: {e}. Activating fallback routing.")
            query_emb = await _safe_embed(query, self.embedding_model)
            closest_slot = None
            if query_emb is not None:
                try:
                    query_emb_str = "[" + ",".join(map(str, query_emb)) + "]"
                    closest_slots = await self.db_pool.fetch("""
                        SELECT topic_key, last_pipeline, (query_embedding <=> $1::vector) as distance
                        FROM session_context_cache
                        WHERE session_id = $2 AND query_embedding IS NOT NULL
                        ORDER BY distance ASC
                        LIMIT 2
                    """, query_emb_str, session_id)
                    if closest_slots:
                        closest_slot = closest_slots[0]
                        d1 = closest_slot['distance']
                        d2 = closest_slots[1]['distance'] if len(closest_slots) > 1 else None
                        gap = (d1 / d2) if (d2 is not None and d2 > 0) else 0.0
                except Exception as db_err:
                    logger.error(f"Failed to query closest slot for fallback: {db_err}")

            if closest_slot:
                logger.info(f"Fallback routing: closest slot is '{closest_slot['topic_key']}' with d1={d1:.4f}, d2={d2}, gap={gap:.4f}")
                if d1 < 0.35 and (d2 is None or gap < 0.65):
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
                elif d1 > 0.55:
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
        if speculative_guess:
            result["speculative_guess"] = speculative_guess
        
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
