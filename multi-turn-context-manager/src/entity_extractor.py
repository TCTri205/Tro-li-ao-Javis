import json
import re
import logging
from datetime import datetime

from router import LLMManager, extract_json
from config import SESSION_PATTERN, SESSION_REGEX

logger = logging.getLogger(__name__)

class EntityExtractor:
    def __init__(self, db_pool, llm_manager: LLMManager):
        self.db_pool = db_pool
        self.llm_manager = llm_manager

    async def extract_and_index(self, conn, session_id: str, cache_slot_id: int, pipeline: str, payload: dict, query: str = None, summary_context: dict = None):
        """
        Extracts entities from the engine payload and indexes them into session_entity_index.
        """
        if summary_context and summary_context.get("entity_id") == "global_aggregate":
            logger.info(f"Skipping entity index extraction for global aggregate cache slot {cache_slot_id}")
            return
            
        logger.info(f"Extracting entities for pipeline {pipeline}, session_id {session_id}, slot {cache_slot_id}")
        entities_to_upsert = [] # List of tuples: (entity_id, entity_type, display_names)

        # 1. SQL Pipeline Extraction
        if pipeline == "SQL":
            rows = payload.get("rows", [])
            # Try to find transcript/session references in rows
            canonical_session = None
            for r in rows:
                for val in r.values():
                    if isinstance(val, str) and SESSION_REGEX.match(val):
                        canonical_session = val
                        break
                if canonical_session:
                    break
            
            # If we don't find it directly in rows, check query
            if not canonical_session and query:
                gts = SESSION_REGEX.findall(query)
                if gts:
                    canonical_session = gts[0].upper()
            
            # If we don't find it directly in rows, check if the session_id matches pattern
            if not canonical_session and SESSION_REGEX.match(session_id):
                canonical_session = session_id
                
            if canonical_session:
                # Retrieve transcript details from DB to build rich display names
                t_row = await conn.fetchrow("""
                    SELECT id, meeting_date, participants, summary
                    FROM transcripts
                    WHERE session_id = $1
                """, canonical_session)
                
                display_names = [
                    canonical_session,
                    f"{canonical_session}.txt",
                    f"{canonical_session}の通話",
                    f"{canonical_session}の会話"
                ]
                
                if t_row:
                    m_date = t_row["meeting_date"]
                    if m_date:
                        d, m, y = m_date.day, m_date.month, m_date.year
                        display_names.extend([
                            f"{y}年{m}月{d}日の通話",
                            f"{m}月{d}日の通話",
                            f"{y}年{m}月{d}日の会話",
                            f"{m}月{d}日の会話"
                        ])
                    
                    # Also register participants as person entities
                    parts = t_row["participants"]
                    if parts:
                        if isinstance(parts, str):
                            try:
                                parts = json.loads(parts)
                            except Exception:
                                parts = []
                        if isinstance(parts, list):
                            for p in parts:
                                if not p:
                                    continue
                                if isinstance(p, dict):
                                    p_clean = str(p.get("name", "")).strip()
                                    p_org = str(p.get("organization", "")).strip() or str(p.get("company", "")).strip()
                                else:
                                    p_clean = str(p).strip()
                                    p_org = ""
                                if p_clean:
                                    p_id = f"{canonical_session}_{p_clean}"
                                    p_base = re.sub(r'(さん|様|さま|君|くん|ちゃん|氏|殿)$', '', p_clean)
                                    p_names = [p_clean, p_base, f"{p_base}さん", f"{p_base}様"]
                                    entities_to_upsert.append((p_id, "person", p_names))
                                if p_org:
                                    org_id = f"{canonical_session}_{p_org}"
                                    org_names = [p_org, f"{p_org}の通話", f"{p_org}の会話"]
                                    entities_to_upsert.append((org_id, "document", org_names))
                                    
                entities_to_upsert.append((canonical_session, "meeting_transcript", display_names))

        # 2. RAG Pipeline Extraction
        elif pipeline == "RAG":
            documents = payload.get("documents", [])
            query_gts = {gt.upper() for gt in SESSION_REGEX.findall(query)} if query else set()
            for doc in documents:
                meta = doc.get("metadata", {})
                file_name = meta.get("file_name") or meta.get("source")
                entity_id = None
                display_names = []
                
                if file_name:
                    entity_id = file_name
                    match = SESSION_REGEX.search(file_name)
                    if match:
                        entity_id = match.group(0)
                elif meta.get("source_table") == "chunks_turn" and meta.get("doc_id"):
                    try:
                        import uuid
                        doc_uuid = uuid.UUID(meta["doc_id"])
                        t_session = await conn.fetchval(
                            "SELECT session_id FROM transcripts WHERE id = $1", doc_uuid
                        )
                        if t_session:
                            entity_id = t_session
                    except Exception as e:
                        logger.error(f"Error resolving doc_id {meta.get('doc_id')} to session_id: {e}")
                        
                if entity_id:
                    # GT Scoping: Only index entities belonging to GTs mentioned in the query.
                    # This prevents cross-session entity pollution from RAG vector retrieval noise.
                    entity_gt_matches = SESSION_REGEX.findall(entity_id.upper())
                    entity_gt = entity_gt_matches[0].upper() if entity_gt_matches else None
                    if query_gts and entity_gt and entity_gt not in query_gts:
                        logger.info(
                            f"RAG Scoping: Skipping entity '{entity_id}' (GT={entity_gt}), "
                            f"not in query GTs {query_gts}"
                        )
                        continue

                    display_names = [
                        entity_id,
                        f"{entity_id}.txt",
                        f"{entity_id}の通話",
                        f"{entity_id}の会話"
                    ]
                        
                    if SESSION_REGEX.match(entity_id):
                        t_row = await conn.fetchrow("""
                            SELECT meeting_date, participants FROM transcripts WHERE session_id = $1
                        """, entity_id)
                        if t_row:
                            m_date = t_row["meeting_date"]
                            if m_date:
                                d, m, y = m_date.day, m_date.month, m_date.year
                                display_names.extend([
                                    f"{y}年{m}月{d}日の通話",
                                    f"{m}月{d}日の通話",
                                    f"{y}年{m}月{d}日の会話",
                                    f"{m}月{d}日の会話"
                                ])
                            parts = t_row["participants"]
                            if parts:
                                if isinstance(parts, str):
                                    try:
                                        parts = json.loads(parts)
                                    except Exception:
                                        parts = []
                                if isinstance(parts, list):
                                    for p in parts:
                                        if not p:
                                            continue
                                        if isinstance(p, dict):
                                            p_clean = str(p.get("name", "")).strip()
                                            p_org = str(p.get("organization", "")).strip() or str(p.get("company", "")).strip()
                                        else:
                                            p_clean = str(p).strip()
                                            p_org = ""
                                        if p_clean:
                                            p_id = f"{entity_id}_{p_clean}"
                                            p_base = re.sub(r'(さん|様|さま|君|くん|ちゃん|氏|殿)$', '', p_clean)
                                            p_names = [p_clean, p_base, f"{p_base}さん", f"{p_base}様"]
                                            entities_to_upsert.append((p_id, "person", p_names))
                                        if p_org:
                                            org_id = f"{entity_id}_{p_org}"
                                            org_names = [p_org, f"{p_org}の通話", f"{p_org}の会話"]
                                            entities_to_upsert.append((org_id, "document", org_names))
                                            
                    entities_to_upsert.append((entity_id, "document" if not SESSION_REGEX.match(entity_id) else "meeting_transcript", display_names))

        # 3. WEB / MODEL Pipeline Extraction
        elif pipeline in ["WEB", "MODEL"]:
            # Call a lightweight LLM extraction model (since there is no structured schema)
            query_used = payload.get("query_used", "")
            results = payload.get("results", [])
            text_context = f"Query: {query_used}\n"
            if results and isinstance(results, list):
                text_context += "Web Results:\n"
                for r in results[:2]:
                    text_context += f"- Title: {r.get('title')}\nSnippet: {r.get('snippet')}\n"
            elif isinstance(payload, dict) and "response" in payload:
                text_context += f"Response: {payload.get('response')}\n"
                
            system_prompt = (
                "あなたはプロのテキスト分析アシスタントです。\n"
                "提供されたテキストから、最大2つの主要なエンティティ（会社名、人名、または重要な文書名など）を抽出してください。\n\n"
                "【禁止事項】\n"
                "「情報」「データ」「内容」「詳細」「こと」「もの」「とき」「結果」などの、極めて一般的で抽象的な単語を `display_names` に含めないでください。これらは代名詞の解決において誤検知を引き起こすため、絶対に避けてください。具体的かつ固有の名称（例: 'トヨタ自動車', '佐藤さん', '歌手A'）のみを抽出してください。\n\n"
                "以下の構造を持つ 'entities' 配列を含む唯一 of JSON オブジェクトを返してください：\n"
                "{\n"
                "  \"entities\": [\n"
                "    {\n"
                "      \"entity_id\": \"エンティティ名（例: 'AJ_Technologies' または 'Toyota'、英数字とアンダースコアを使用）\",\n"
                "      \"entity_type\": \"person\" | \"document\" | \"sql_result\",\n"
                "      \"display_names\": [\"正式名称\", \"それに対応する日本語の固有の別称（例: 'トヨタ', 'AJ社' など）\"]\n"
                "    }\n"
                "  ]\n"
                "}\n"
                "JSON以外の説明やMarkdownの装飾は一切含めないでください。"
            )

            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text_context}
            ]
            
            try:
                response = await self.llm_manager.generate_chat_completion(
                    messages=messages, response_format={"type": "json_object"}
                )
                data = extract_json(response)
                for ent in data.get("entities", []):
                    e_id = ent.get("entity_id")
                    e_type = ent.get("entity_type")
                    d_names = ent.get("display_names", [])
                    if e_id and e_type and d_names:
                        entities_to_upsert.append((e_id, e_type, d_names))
            except Exception as e:
                logger.error(f"Failed to extract entities via LLM for WEB/MODEL: {e}")

        # 4. Perform DB UPSERT
        ALLOWED_TYPES = {'meeting_transcript', 'person', 'document', 'sql_result'}
        
        # Deduplicate entities by (entity_id, entity_type) and merge display_names
        unique_entities = {}
        for e_id, e_type, d_names in entities_to_upsert:
            # Sanitize entity type
            e_type_clean = e_type.strip()
            if e_type_clean not in ALLOWED_TYPES:
                if e_type_clean.lower() in ('company', 'organization', 'object', 'thing', 'location'):
                    e_type_clean = 'document'
                elif e_type_clean.lower() in ('user', 'human', 'employee'):
                    e_type_clean = 'person'
                else:
                    e_type_clean = 'document'
            
            key = (e_id, e_type_clean)
            if key not in unique_entities:
                unique_entities[key] = set()
            for n in d_names:
                if n.strip():
                    unique_entities[key].add(n.strip())

        for (e_id, e_type_clean), clean_names_set in unique_entities.items():
            try:
                clean_names = list(clean_names_set)
                await conn.execute("""
                    INSERT INTO session_entity_index (session_id, cache_slot_id, entity_id, entity_type, display_names)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (session_id, entity_id) 
                    DO UPDATE SET 
                        display_names = ARRAY(
                            SELECT DISTINCT x 
                            FROM unnest(session_entity_index.display_names || EXCLUDED.display_names) AS x
                        )
                """, session_id, cache_slot_id, e_id, e_type_clean, clean_names)
                logger.info(f"UPSERT entity {e_id} ({e_type_clean}) for session {session_id} successful.")
            except Exception as e:
                logger.error(f"Error during UPSERT entity {e_id}: {e}")
