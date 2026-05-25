import os
import json
import sys

# Configure stdout and stderr to output UTF-8 text on Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Add parent directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.retriever import JavisRetriever

def run_tests():
    workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_dir = os.path.join(workspace_dir, "database", "database.db")
    test_cases_path = os.path.join(workspace_dir, "database", "test_cases.json")
    
    if not os.path.exists(test_cases_path):
        print(f"Error: Test cases file not found at {test_cases_path}")
        return
        
    with open(test_cases_path, "r", encoding="utf-8") as f:
        test_cases = json.load(f)
        
    print(f"Connecting to JavisRetriever at {db_dir}...")
    try:
        retriever = JavisRetriever(db_dir)
    except Exception as e:
        print(f"Error loading JavisRetriever: {e}. Did you run build_db.py first?")
        return
        
    print("\n" + "="*50)
    print("RUNNING RETRIEVAL TEST SUITE (VIA JAVIS RETRIEVER)")
    print("="*50 + "\n")
    
    for case in test_cases:
        case_id = case["id"]
        group = case["group"]
        query = case["query"]
        intent = case["intent"]
        expected_keywords = case.get("expected_keywords", [])
        
        print(f"Test Case {case_id} [{group} / {intent}]")
        print(f"Query: \"{query}\"")
        
        # Run query via JavisRetriever
        try:
            document_objs = retriever.retrieve(query, intent)
        except Exception as e:
            print(f"Retrieval error: {e}")
            print("Status: FAIL (Retrieval raised error)")
            print("\n" + "="*50 + "\n")
            continue
            
        print(f"Retrieved {len(document_objs)} document(s):")
        
        # Check keyword matches
        combined_text = "\n".join([doc.page_content for doc in document_objs])
        matched_keywords = [kw for kw in expected_keywords if kw in combined_text]
        match_rate = len(matched_keywords) / len(expected_keywords) if expected_keywords else 1.0
        
        for idx, doc in enumerate(document_objs):
            meta = doc.metadata
            print(f"  Result #{idx+1}:")
            print(f"    Source File: {meta.get('source_file')}")
            # Print specific metadata depending on collection type
            if group == "aj_docs":
                print(f"    Category: {meta.get('category')} | Company: {meta.get('company_name')}")
                if meta.get('product_name'):
                    print(f"    Products: {meta.get('product_name')}")
            else:
                print(f"    Section {meta.get('section_id')}: {meta.get('section_name')}")
            
            # Print content preview
            preview = doc.page_content.replace('\n', ' ')
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
