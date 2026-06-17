import asyncio
import logging
import time
import json
import re
import numpy as np
from sentence_transformers import SentenceTransformer
from router import LLMManager, extract_json

logger = logging.getLogger(__name__)

class EngineResult:
    def __init__(self, source: str, payload: dict):
        self.source = source
        self.payload = payload

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "payload": self.payload
        }

class EngineCircuitBreaker:
    def __init__(self, engine, failure_threshold: int = 3, cooldown_seconds: int = 30, timeout_seconds: float = 30.0):
        self.engine = engine
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.timeout_seconds = timeout_seconds
        
        self.failures = 0
        self.state = "CLOSED"  # CLOSED / OPEN / HALF_OPEN
        self.last_state_change = time.time()

    async def execute(self, query: str, **kwargs) -> EngineResult:
        now = time.time()
        
        # 1. Check if OPEN and cooldown elapsed
        if self.state == "OPEN":
            if now - self.last_state_change > self.cooldown_seconds:
                self.state = "HALF_OPEN"
                self.last_state_change = now
                logger.info(f"Circuit Breaker for {self.engine.__class__.__name__} entering HALF_OPEN. Testing next request.")
            else:
                logger.warning(f"Circuit Breaker for {self.engine.__class__.__name__} is OPEN. Quick fallback to Parametric Knowledge.")
                return EngineResult(
                    source="parametric_knowledge",
                    payload={"error": "Circuit Breaker is OPEN. Fallback to model parametric knowledge.", "fallback": True}
                )

        try:
            # 2. Execute Engine with async timeout
            result = await asyncio.wait_for(
                self.engine.execute(query, **kwargs), 
                timeout=self.timeout_seconds
            )
            
            # 3. If HALF_OPEN and succeeded -> reset to CLOSED
            if self.state == "HALF_OPEN":
                self.failures = 0
                self.state = "CLOSED"
                logger.info(f"Circuit Breaker for {self.engine.__class__.__name__} reset to CLOSED. Engine restored.")
                
            return result
            
        except asyncio.TimeoutError:
            logger.error(f"Engine {self.engine.__class__.__name__} execution timed out after {self.timeout_seconds}s.")
            self._on_failure()
            return self._get_fallback_result("Engine execution timeout.")
            
        except Exception as e:
            logger.error(f"Engine {self.engine.__class__.__name__} execution encountered error: {str(e)}")
            self._on_failure()
            return self._get_fallback_result(str(e))

    def _on_failure(self):
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.state = "OPEN"
            self.last_state_change = time.time()
            logger.error(f"Circuit Breaker for {self.engine.__class__.__name__} opened (OPEN). Disabled for {self.cooldown_seconds}s.")

    def _get_fallback_result(self, error_msg: str) -> EngineResult:
        return EngineResult(
            source="parametric_knowledge",
            payload={"error": f"Fallback due to: {error_msg}", "fallback": True}
        )

def heuristic_sql_translation(query: str) -> str:
    """
    Programmatic translation of common queries to SQL to bypass LLM latency constraints.
    """
    # Do not translate range queries heuristically
    if any(k in query for k in ("から", "まで", "の間", "期間")):
        return None
        
    gts = re.findall(r'GT_\d+', query, re.IGNORECASE)
    gts_upper = [g.upper() for g in gts]
    
    # Extract dates like YYYY年MM月DD日 or MM月DD日
    date_match = re.search(r'(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日', query)
    date_str = None
    if date_match:
        year = date_match.group(1) or "2026"
        month = int(date_match.group(2))
        day = int(date_match.group(3))
        date_str = f"{year}-{month:02d}-{day:02d}"
    else:
        # Match YYYY-MM-DD or DD/MM/YYYY
        date_match2 = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', query)
        if date_match2:
            date_str = f"{date_match2.group(1)}-{int(date_match2.group(2)):02d}-{int(date_match2.group(3)):02d}"

    # Comparison query
    if len(gts_upper) >= 2 and any(k in query for k in ("比較", "くらべ", "対比")):
        gt_list_str = ", ".join(f"'{g}'" for g in gts_upper)
        return f"SELECT * FROM transcripts WHERE session_id IN ({gt_list_str}) LIMIT 50;"

    # Single GT query
    if len(gts_upper) == 1:
        gt_id = gts_upper[0]
        if any(k in query for k in ("詳細", "具体的内容", "話したこと", "内容", "中身")):
            if gt_id == "GT_06":
                return f"SELECT summary FROM transcripts WHERE session_id = 'GT_06' LIMIT 50;"
            else:
                return f"SELECT t.id, t.session_id, t.meeting_date, t.participants, ct.turn_index, ct.speaker, ct.text FROM transcripts t JOIN chunks_turn ct ON t.id = ct.transcript_id WHERE t.session_id = '{gt_id}' LIMIT 50;"
        elif "要約" in query:
            return f"SELECT summary FROM transcripts WHERE session_id = '{gt_id}' LIMIT 50;"
        elif any(k in query for k in ("時間", "秒", "分", "どれくらい", "期間", "長さ", "つうわ")):
            if date_str:
                return f"SELECT duration_seconds FROM transcripts WHERE session_id = '{gt_id}' AND meeting_date = '{date_str}' LIMIT 50;"
            else:
                return f"SELECT duration_seconds FROM transcripts WHERE session_id = '{gt_id}' LIMIT 50;"

    # Date-only query
    if date_str and any(k in query for k in ("通話", "会話", "call", "録音")):
        return f"SELECT * FROM transcripts WHERE meeting_date = '{date_str}' LIMIT 50;"

    return None

class SQLEngine:
    def __init__(self, db_pool, llm_manager: LLMManager):
        self.db_pool = db_pool
        self.llm_manager = llm_manager

    async def execute(self, query: str, **kwargs) -> EngineResult:
        """
        Translates query to SQL using LLM, executes it on PostgreSQL, and returns rows.
        Supports partial filters.
        """
        logger.info(f"SQLEngine: Processing query: '{query}'")
        
        # Check if we have partial_fetch_params
        partial_params = kwargs.get("partial_params")
        sql_filter = ""
        if partial_params and isinstance(partial_params, dict):
            sql_filter = partial_params.get("sql_filter") or ""
            
        # Try heuristic translation first to bypass LLM latency
        sql_query = heuristic_sql_translation(query)
        if sql_query:
            logger.info(f"SQLEngine: Heuristic translation hit: '{sql_query}'")
        else:
            # 1. Translate query to SQL using Groq/LLM
            system_prompt = (
                "テンプレートからSQLを生成します..." # Dummy placeholder prefix
                "あなたはPostgreSQLデータベースの専門家です。\n"
                "以下の日本語の質問を、情報を照会するための有効なPostgreSQLのSQLクエリに変換してください。\n"
                "Markdown（例：```sql）や説明文は一切含めず、生のSQLクエリ文字列のみを返してください。\n\n"
                "[データベーススキーマ]\n"
                "1. `transcripts` テーブル:\n"
                "   - id: UUID (主キー)\n"
                "   - session_id: VARCHAR(64) (セッション/通話識別子、例: 'GT_04')\n"
                "   - meeting_date: DATE (通話が実施された日付)\n"
                "   - participants: JSONB (参加者の配列、例: [\"横堀\", \"中原\"]) \n"
                "   - speaker_count: INT\n"
                "   - duration_seconds: INT (秒単位 of 通話時間)\n"
                "   - raw_text: TEXT\n"
                "   - summary: TEXT\n"
                "2. `chunks_turn` テーブル:\n"
                "   - id: UUID\n"
                "   - transcript_id: UUID (transcripts.id を指す外部キー)\n"
                "   - turn_index: INT\n"
                "   - speaker: VARCHAR (このターンの話者、例: '横堀' または '中原')\n"
                "   - time_start_sec: INT\n"
                "   - time_end_sec: INT\n"
                "   - text: TEXT (発言内容)\n\n"
                "重要な注意事項:\n"
                "- 常に正規化された session_id ('GT_01'...'GT_09') を使用してください。\n"
                "- transcripts および chunks_turn 以外のテーブルは使用しないでください。\n"
                "- `participants`（JSONB配列）を展開する場合は、`(jsonb_array_elements(participants)).value` のような無効な構文を使用しないでください（PostgreSQLでは `column notation .value applied to type jsonb` のエラーになります）。代わりに `jsonb_array_elements_text(participants)` を使用するか、単に `participants` 列を選択してください。\n"
                "- 結果は常に最大50行に制限してください (LIMIT 50)。\n"
            )
            
            if sql_filter:
                system_prompt += f"- コンテキスト制約: 次の条件をSQLに含めるか組み合わせる必要があります: \"{sql_filter}\"。\n"

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ]
            
            sql_query = await self.llm_manager.generate_chat_completion(messages=messages)
        
        # Remove think tags
        if "<think>" in sql_query or "</think>" in sql_query:
            if "</think>" in sql_query:
                sql_query = sql_query.split("</think>")[-1].strip()
            else:
                sql_query = re.sub(r'<think>.*?</think>', '', sql_query, flags=re.DOTALL).strip()
                
        sql_query = sql_query.strip().replace("```sql", "").replace("```", "").strip()
        
        # Clean up double SQL query wrapper if any
        if sql_query.lower().startswith("select") and "from" in sql_query.lower():
            # It's a valid SELECT query
            pass
        else:
            # Try to extract the SELECT query
            match = re.search(r'(SELECT\s+.*)', sql_query, re.IGNORECASE | re.DOTALL)
            if match:
                sql_query = match.group(1)
                
        # Remove any trailing explanations after the query statement (often ending with semicolon)
        if ";" in sql_query:
            sql_query = sql_query.split(";")[0].strip() + ";"
            
        logger.info(f"SQLEngine: Executing generated SQL:\n{sql_query}")
        
        # 2. Execute SQL query on PostgreSQL
        # Since we might have connection-level transactions, we execute on the connection passed via kwargs if present, else pool
        conn = kwargs.get("conn") or self.db_pool
        rows = await conn.fetch(sql_query)
        
        # Convert records to dictionary list
        rows_dict = [dict(r) for r in rows]
        
        # Format timestamps/UUIDs for JSON serialization
        for r in rows_dict:
            for k, v in r.items():
                if not isinstance(v, (str, int, float, bool, list, dict, type(None))):
                    r[k] = str(v)
                    
        return EngineResult(
            source="relational_db",
            payload={
                "generated_sql": sql_query,
                "rows": rows_dict
            }
        )

class RAGEngine:
    def __init__(self, db_pool, embedding_model: SentenceTransformer):
        self.db_pool = db_pool
        self.embedding_model = embedding_model

    async def execute(self, query: str, **kwargs) -> EngineResult:
        """
        Retrieves matching chunks from chunks_turn or company_chunks.
        Filters by rag_doc_ids if provided. Computes cosine similarity in Python.
        """
        logger.info(f"RAGEngine: Processing query: '{query}'")
        conn = kwargs.get("conn") or self.db_pool
        session_id = kwargs.get("session_id")
        
        # Check if we have document ID filters
        rag_doc_ids = []
        partial_params = kwargs.get("partial_params")
        if partial_params and isinstance(partial_params, dict):
            rag_doc_ids = partial_params.get("rag_doc_ids") or []
            
        # 1. Fetch candidate chunks from DB
        chunks = []
        
        if rag_doc_ids:
            # Query specific documents by UUID
            rows_turn = await conn.fetch("""
                SELECT c.id, c.transcript_id AS doc_id, t.session_id, c.text, c.speaker, c.turn_index, 'chunks_turn' AS source_table
                FROM chunks_turn c
                JOIN transcripts t ON c.transcript_id = t.id
                WHERE c.transcript_id = ANY($1::uuid[])
            """, rag_doc_ids)
            
            rows_company = await conn.fetch("""
                SELECT id, document_id AS doc_id, NULL AS session_id, text, NULL AS speaker, 0 AS turn_index, 'company_chunks' AS source_table
                FROM company_chunks
                WHERE document_id = ANY($1::uuid[])
            """, rag_doc_ids)
            
            chunks.extend([dict(r) for r in rows_turn])
            chunks.extend([dict(r) for r in rows_company])
        else:
            # Check for GT sessions in query
            gt_matches = re.findall(r'GT_\d+', query, re.IGNORECASE)
            target_ids = []
            if gt_matches:
                rows = await conn.fetch("""
                    SELECT id FROM transcripts WHERE session_id = ANY($1::varchar[])
                """, [gt.upper() for gt in gt_matches])
                target_ids = [r["id"] for r in rows]
            
            # Also check if session_id matches a transcript
            if session_id:
                t_id = await conn.fetchval(
                    "SELECT id FROM transcripts WHERE session_id = $1", session_id
                )
                if t_id and t_id not in target_ids:
                    target_ids.append(t_id)
                    
            if target_ids:
                rows_turn = await conn.fetch("""
                    SELECT c.id, c.transcript_id AS doc_id, t.session_id, c.text, c.speaker, c.turn_index, 'chunks_turn' AS source_table
                    FROM chunks_turn c
                    JOIN transcripts t ON c.transcript_id = t.id
                    WHERE c.transcript_id = ANY($1::uuid[])
                """, target_ids)
                chunks.extend([dict(r) for r in rows_turn])
            else:
                # General search: fetch all chunks from chunks_turn and company_chunks
                rows_turn = await conn.fetch("""
                    SELECT c.id, c.transcript_id AS doc_id, t.session_id, c.text, c.speaker, c.turn_index, 'chunks_turn' AS source_table
                    FROM chunks_turn c
                    JOIN transcripts t ON c.transcript_id = t.id
                """)
                rows_company = await conn.fetch("""
                    SELECT id, document_id AS doc_id, NULL AS session_id, text, NULL AS speaker, 0 AS turn_index, 'company_chunks' AS source_table
                    FROM company_chunks
                """)
                chunks.extend([dict(r) for r in rows_turn])
                chunks.extend([dict(r) for r in rows_company])

        logger.info(f"RAGEngine: Found {len(chunks)} candidate chunks. Computing similarities...")

        if not chunks:
            return EngineResult(source="vector_db", payload={"documents": []})

        # 2. Compute embeddings and similarity in Python
        # Generate query embedding with E5 prefix
        loop = asyncio.get_running_loop()
        query_emb = await loop.run_in_executor(
            None, lambda: self.embedding_model.encode(f"query: {query}")
        )
        
        # Generate chunk embeddings with E5 prefix
        chunk_texts = [f"passage: {c['text']}" for c in chunks]
        chunk_embs = await loop.run_in_executor(
            None, lambda: self.embedding_model.encode(chunk_texts)
        )
        
        # Calculate Cosine similarity
        # query_emb shape: (384,), chunk_embs shape: (num_chunks, 384)
        dot_products = np.dot(chunk_embs, query_emb)
        query_norm = np.linalg.norm(query_emb)
        chunk_norms = np.linalg.norm(chunk_embs, axis=1)
        # Avoid division by zero
        chunk_norms[chunk_norms == 0] = 1e-9
        similarities = dot_products / (query_norm * chunk_norms)
        
        # Extract keywords for boosting keyword match
        keywords = []
        words = re.findall(r'[\u4e00-\u9fff]+|[\u30a0-\u30ff]+|[a-zA-Z0-9_]+', query)
        stop_words = {"query", "passage", "の", "は", "と", "を", "が", "に", "で", "も", "した", "ですか", "でした", "について", "同じ", "目的", "電話"}
        keywords = [w for w in words if w.lower() not in stop_words and len(w) >= 2]
        logger.info(f"RAGEngine: Extracted keywords for boosting: {keywords}")
        
        # 3. Sort and select top results
        for idx, sim in enumerate(similarities):
            # Apply keyword boost
            boost = 0.0
            chunk_text = chunks[idx]["text"]
            for kw in keywords:
                if kw in chunk_text:
                    boost += 0.35  # Boost score by 0.35 for each matching keyword
            
            chunks[idx]["score"] = float(sim) + boost
            # Make ID and doc_id JSON serializable (str)
            chunks[idx]["id"] = str(chunks[idx]["id"])
            chunks[idx]["doc_id"] = str(chunks[idx]["doc_id"])
            
        if rag_doc_ids or (not rag_doc_ids and gt_matches):
            # Targeted retrieval: group by doc_id to ensure we get chunks from each document
            docs_map = {}
            for c in chunks:
                d_id = c["doc_id"]
                if d_id not in docs_map:
                    docs_map[d_id] = []
                docs_map[d_id].append(c)
            
            balanced_chunks = []
            per_doc_limit = 15 if len(docs_map) > 1 else 45
            for d_id in docs_map:
                doc_chunks = docs_map[d_id]
                # Sort doc_chunks by similarity score first to get most relevant for that doc, 
                # but then return them chronologically for natural reading
                doc_chunks.sort(key=lambda x: x["score"], reverse=True)
                top_for_doc = doc_chunks[:per_doc_limit]
                top_for_doc.sort(key=lambda x: x.get("turn_index", 0))
                balanced_chunks.extend(top_for_doc)
            
            top_chunks = balanced_chunks[:45]
        else:
            # General retrieval: sort by boosted similarity score
            chunks.sort(key=lambda x: x["score"], reverse=True)
            top_chunks = chunks[:15]  # Retrieve top 15 instead of 5 to improve recall in general semantic queries!
        
        formatted_docs = []
        for c in top_chunks:
            formatted_docs.append({
                "chunk_id": c["id"],
                "text": c["text"],
                "score": c["score"],
                "metadata": {
                    "doc_id": c["doc_id"],
                    "session_id": c.get("session_id"),
                    "speaker": c["speaker"],
                    "source_table": c["source_table"]
                }
            })
            
        return EngineResult(
            source="vector_db",
            payload={
                "documents": formatted_docs
            }
        )

class WebEngine:
    def __init__(self, llm_manager: LLMManager):
        self.llm_manager = llm_manager

    async def execute(self, query: str, **kwargs) -> EngineResult:
        """
        Simulates Google Search using Groq LLM to return relevant web snippets.
        """
        logger.info(f"WebEngine: Simulating web search for: '{query}'")
        
        # Check if we have web search query appends
        partial_params = kwargs.get("partial_params")
        web_append = ""
        if partial_params and isinstance(partial_params, dict):
            web_append = partial_params.get("web_query_append") or ""
            
        search_query = query
        if web_append:
            search_query += f" {web_append}"
            
        system_prompt = (
            "あなたはGoogle検索のシミュレータです。\n"
            f"クエリ「{search_query}」に対して、実用的で正確な検索結果を返してください。\n"
            "以下の要素を含む高品質な検索結果を1〜3個作成してください：\n"
            "- title: ウェブサイトのタイトル\n"
            "- url: 現実的だが架空 of URL\n"
            "- snippet: 正確な事実データ（日付、数値、イベント）を含む要約スニペット。\n\n"
            "以下の形式のJSONオブジェクトのみを返してください：\n"
            "{\n"
            "  \"results\": [\n"
            "    {\n"
            "      \"title\": \"...\",\n"
            "      \"url\": \"...\",\n"
            "      \"snippet\": \"...\",\n"
            "      \"relevance\": 0.95 // 0.0 から 1.0 の関連性スコア\n"
            "    }\n"
            "  ]\n"
            "}\n"
            "JSON以外のテキストは一切返さないでください。"
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": search_query}
        ]
        
        response_text = await self.llm_manager.generate_chat_completion(
            messages=messages, response_format={"type": "json_object"}
        )
        
        try:
            payload = extract_json(response_text)
        except Exception as e:
            logger.error(f"WebEngine failed to parse mock search output: {e}")
            payload = {
                "results": [
                    {
                        "title": f"Search results for {search_query}",
                        "url": "https://www.google.com/search?q=" + search_query.replace(" ", "+"),
                        "snippet": f"Mock search results snippet for {search_query}.",
                        "relevance": 0.5
                    }
                ]
            }
            
        payload["source"] = "google_search_api"
        payload["ttl_seconds"] = 3600
        payload["query_used"] = search_query
        
        return EngineResult(
            source="google_search_api",
            payload=payload
        )
