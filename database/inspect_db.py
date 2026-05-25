import sys
import os

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.chroma_client import get_chroma_client, get_embedding_function

client = get_chroma_client(os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.db"))
emb = get_embedding_function()

print("=== COLLECTIONS ===")
colls = client.list_collections()
for c in colls:
    print(f"  - {c.name}")

print()
print("=== aj_docs COLLECTION (all docs) ===")
aj = client.get_collection("aj_docs", embedding_function=emb)
result = aj.get(include=["documents", "metadatas"])
for i, (doc, meta) in enumerate(zip(result["documents"], result["metadatas"])):
    src  = meta.get("source_file", "")
    cat  = meta.get("category", "")
    comp = meta.get("company_name", "")
    prod = meta.get("product_name", "")
    sect = meta.get("section_title", "")
    preview = doc[:150].replace("\n", " ")
    print(f"  [{i}] {src} | {cat} | {comp} | product={prod}")
    print(f"       section: {sect}")
    print(f"       preview: {preview}")
    print()

print()
print("=== summary_transcripts COLLECTION (all docs) ===")
sm = client.get_collection("summary_transcripts", embedding_function=emb)
result2 = sm.get(include=["documents", "metadatas"])
for i, (doc, meta) in enumerate(zip(result2["documents"], result2["metadatas"])):
    sid  = meta.get("section_id", "")
    sname= meta.get("section_name", "")
    cust = meta.get("customer_name", "")
    preview = doc[:150].replace("\n", " ")
    print(f"  [{i}] section_id={sid} | section_name={sname} | customer={cust}")
    print(f"       preview: {preview}")
    print()
