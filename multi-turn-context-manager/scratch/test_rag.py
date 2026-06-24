import asyncio
import os
import sys
import json
import numpy as np
from dotenv import load_dotenv
import asyncpg

# Reconfigure stdout to support UTF-8 on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tests')))

from router import get_llm_manager, _safe_embed
from orchestrator import IntelligentOrchestrator
from test_suite_v3 import MockSentenceTransformer

load_dotenv()
DB_URL = os.getenv("NUMERIC_SQL_DATABASE_URL")

async def main():
    conn = await asyncpg.connect(DB_URL)
    embedding_model = MockSentenceTransformer()
    
    query = "GT_03の通話とGT_09の通話において、アセットジャパンはそれぞれどのような立場（例: 受付担当者、物件所有者、仲介業者など）で登場しましたか？"
    session_id = "v3h_deep_chain"
    
    # Let's run the exact logic of RAGEngine
    import re
    SESSION_REGEX = re.compile(r'\b(?:GT|SESSION|SESS|RECORD|TR)[-_]?\d+(?![a-zA-Z0-9])', re.IGNORECASE | re.ASCII)
    
    gt_matches = set(gt.upper() for gt in SESSION_REGEX.findall(query))
    print("Initial gt_matches from query:", gt_matches)
    
    words = re.findall(r'[\u4e00-\u9fff]+|[\u30a0-\u30ff]+|[a-zA-Z0-9_]+', query)
    stop_words = {"query", "passage", "の", "は", "と", "を", "が", "に", "で", "も", "した", "ですか", "でした", "について", "同じ", "目的", "電話"}
    keywords = [w for w in words if w.lower() not in stop_words and len(w) >= 2]
    clean_keywords = []
    for kw in keywords:
        clean_kw = re.sub(r'(さん|様|さま|君|くん|ちゃん|氏|殿)$', '', kw)
        if clean_kw:
            clean_keywords.append(clean_kw)
        clean_keywords.append(kw)
    clean_keywords = list(set(clean_keywords))
    print("Clean keywords:", clean_keywords)

    if session_id and clean_keywords:
        for kw in clean_keywords:
            if len(kw) >= 2:
                ent_rows = await conn.fetch("""
                    SELECT entity_id FROM session_entity_index 
                    WHERE session_id = $1 AND array_to_string(display_names, ' ') LIKE $2
                """, session_id, f"%{kw}%")
                for er in ent_rows:
                    gts = SESSION_REGEX.findall(er["entity_id"])
                    if gts:
                        gt_matches.add(gts[0].upper())
                        
    print("gt_matches after entity index lookup:", gt_matches)

    if clean_keywords:
        for kw in clean_keywords:
            if len(kw) >= 2:
                rows = await conn.fetch("""
                    SELECT session_id FROM transcripts 
                    WHERE participants::text ILIKE $1
                    LIMIT 5
                """, f"%{kw}%")
                for r in rows:
                    if r["session_id"]:
                        gt_matches.add(r["session_id"].upper())
                        
    print("gt_matches after fallback direct search:", gt_matches)

    target_ids = []
    if gt_matches:
        rows = await conn.fetch("""
            SELECT id, session_id FROM transcripts WHERE session_id = ANY($1::varchar[])
        """, list(gt_matches))
        target_ids = [r["id"] for r in rows]
        print("Target IDs mapping:", {r["session_id"]: str(r["id"]) for r in rows})
        
    chunks = []
    if target_ids:
        rows_turn = await conn.fetch("""
            SELECT c.id, c.transcript_id AS doc_id, t.session_id, c.text, c.speaker, c.turn_index, 'chunks_turn' AS source_table
            FROM chunks_turn c
            JOIN transcripts t ON c.transcript_id = t.id
            WHERE c.transcript_id = ANY($1::uuid[])
        """, target_ids)
        chunks.extend([dict(r) for r in rows_turn])

        rows_trans = await conn.fetch("""
            SELECT id AS doc_id, session_id, raw_text, summary, 'transcripts' AS source_table
            FROM transcripts
            WHERE id = ANY($1::uuid[])
        """, target_ids)
        for r in rows_trans:
            if r["summary"]:
                chunks.append({
                    "id": f"{r['session_id']}_summary",
                    "doc_id": str(r["doc_id"]),
                    "session_id": r["session_id"],
                    "text": f"通話の要約: {r['summary']}",
                    "speaker": "System",
                    "turn_index": -1,
                    "source_table": "transcripts"
                })
            if r["raw_text"]:
                chunks.append({
                    "id": f"{r['session_id']}_raw_text",
                    "doc_id": str(r["doc_id"]),
                    "session_id": r["session_id"],
                    "text": f"通話のログ全体:\n{r['raw_text']}",
                    "speaker": "System",
                    "turn_index": -2,
                    "source_table": "transcripts"
                })
                
    print(f"Total candidate chunks: {len(chunks)}")
    
    # Let's run similarity and boost
    query_emb = embedding_model.encode(f"query: {query}")
    chunk_texts = [f"passage: {c['text']}" for c in chunks]
    chunk_embs = embedding_model.encode(chunk_texts)
    
    dot_products = np.dot(chunk_embs, query_emb)
    query_norm = np.linalg.norm(query_emb)
    chunk_norms = np.linalg.norm(chunk_embs, axis=1)
    query_norm_val = query_norm if query_norm != 0 else 1e-9
    chunk_norms[chunk_norms == 0] = 1e-9
    similarities = dot_products / (query_norm_val * chunk_norms)
    
    # Keywords for boosting
    keywords = []
    for kw in clean_keywords:
        clean_kw = re.sub(r'(さん|様|さま|君|くん|ちゃん|氏|殿)$', '', kw)
        if clean_kw:
            keywords.append(clean_kw)
        keywords.append(kw)
    keywords = list(set(keywords))
    
    for idx, sim in enumerate(similarities):
        boost = 0.0
        chunk_text = chunks[idx]["text"]
        for kw in keywords:
            if kw in chunk_text:
                boost += 0.35
        if chunks[idx].get("source_table") == "transcripts":
            boost += 0.5
        chunks[idx]["score"] = float(sim) + boost
        chunks[idx]["similarity"] = float(sim)
        chunks[idx]["boost"] = boost
        chunks[idx]["id"] = str(chunks[idx]["id"])
        chunks[idx]["doc_id"] = str(chunks[idx]["doc_id"])

    # Targeted grouping
    docs_map = {}
    for c in chunks:
        d_id = c["doc_id"]
        if d_id not in docs_map:
            docs_map[d_id] = []
        docs_map[d_id].append(c)
        
    print(f"Documents found in map: {list(docs_map.keys())}")
    for d_id, doc_chunks in docs_map.items():
        sess = doc_chunks[0]['session_id']
        print(f"  Doc {d_id} ({sess}) has {len(doc_chunks)} chunks")
        
    balanced_chunks = []
    per_doc_limit = max(1, 45 // len(docs_map)) if len(docs_map) > 1 else 45
    for d_id in docs_map:
        doc_chunks = docs_map[d_id]
        doc_chunks.sort(key=lambda x: x["score"], reverse=True)
        top_for_doc = doc_chunks[:per_doc_limit]
        top_for_doc.sort(key=lambda x: x.get("turn_index", 0))
        balanced_chunks.extend(top_for_doc)
        
    top_chunks = balanced_chunks[:45]
    print(f"Selected {len(top_chunks)} final top chunks.")
    
    # Check if GT_09 is present in top_chunks
    gt09_chunks = [c for c in top_chunks if c.get("session_id") == "GT_09"]
    print(f"GT_09 chunks in final top chunks: {len(gt09_chunks)}")
    for c in gt09_chunks[:3]:
        print(f"  Score: {c['score']:.4f} | Text: {c['text'][:100]}")
        
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
