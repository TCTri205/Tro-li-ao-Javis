import os
import json
import sys

# Configure stdout and stderr to output UTF-8 text on Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Add parent directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.chroma_client import get_chroma_client, get_embedding_function

def run_tests():
    workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_dir = os.path.join(workspace_dir, "database", "database.db")
    test_cases_path = os.path.join(workspace_dir, "database", "test_cases.json")
    
    if not os.path.exists(test_cases_path):
        print(f"Error: Test cases file not found at {test_cases_path}")
        return
        
    with open(test_cases_path, "r", encoding="utf-8") as f:
        test_cases = json.load(f)
        
    print(f"Connecting to ChromaDB at {db_dir}...")
    client = get_chroma_client(db_dir)
    embedding_func = get_embedding_function()
    
    # Load collections
    try:
        aj_collection = client.get_collection("aj_docs", embedding_function=embedding_func)
        summary_collection = client.get_collection("summary_transcripts", embedding_function=embedding_func)
    except Exception as e:
        print(f"Error loading collections: {e}. Did you run build_db.py first?")
        return
        
    print("\n" + "="*50)
    print("RUNNING RETRIEVAL TEST SUITE")
    print("="*50 + "\n")
    
    for case in test_cases:
        case_id = case["id"]
        group = case["group"]
        query = case["query"]
        intent = case["intent"]
        expected_keywords = case.get("expected_keywords", [])
        
        print(f"Test Case {case_id} [{group} / {intent}]")
        print(f"Query: \"{query}\"")
        
        # Determine target collection
        if group == "aj_docs":
            collection = aj_collection
        else:
            collection = summary_collection
            
        # Run query (retrieve top 3 results)
        results = collection.query(
            query_texts=[query],
            n_results=3
        )
        
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0] if "distances" in results else [0.0] * len(documents)
        
        print(f"Retrieved {len(documents)} document(s):")
        
        # Check keyword matches
        combined_text = "\n".join(documents)
        matched_keywords = [kw for kw in expected_keywords if kw in combined_text]
        match_rate = len(matched_keywords) / len(expected_keywords) if expected_keywords else 1.0
        
        for idx, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances)):
            print(f"  Result #{idx+1} (Distance: {dist:.4f}):")
            print(f"    Source File: {meta.get('source_file')}")
            # Print specific metadata depending on collection type
            if group == "aj_docs":
                print(f"    Category: {meta.get('category')} | Company: {meta.get('company_name')}")
                if meta.get('product_name'):
                    print(f"    Products: {meta.get('product_name')}")
            else:
                print(f"    Section {meta.get('section_id')}: {meta.get('section_name')}")
            
            # Print content preview
            preview = doc.replace('\n', ' ')
            if len(preview) > 150:
                preview = preview[:150] + "..."
            print(f"    Content: {preview}")
            print("-" * 30)
            
        print(f"Keyword Matches: {len(matched_keywords)}/{len(expected_keywords)} ({match_rate*100:.1f}%)")
        print(f"Matched: {matched_keywords}")
        if match_rate >= 0.5:
            print("Status: PASS")
        else:
            print("Status: FAIL (Low keyword match rate)")
            
        print("\n" + "="*50 + "\n")

if __name__ == "__main__":
    run_tests()
