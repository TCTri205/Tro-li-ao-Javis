import json
import re
import sys

# Reconfigure output to support utf-8 print statements
sys.stdout.reconfigure(encoding='utf-8')

v1_path = r"D:\VJ\Tro-li-ao-Javis\multi-turn-context-manager\test_results_v1.json"
with open(v1_path, 'r', encoding='utf-8') as f:
    v1_results = json.load(f)

def normalize_query(q):
    if not q:
        return ""
    q = re.sub(r'[\s\?\？\！\!\,\，\.\．\-\:\：\(\)\（\）\"\'\“\”\[\]\{\}\<\>\_、。ー]', '', q).lower()
    q = q.replace('of', '').replace('の', '')
    return q

q_csv = 'GT_04とGT_06の通話を比較してください。'
q_csv_norm = normalize_query(q_csv)
print(f"CSV query: {q_csv}")
print(f"CSV query normalized: {q_csv_norm}")
print("-" * 50)

for r in v1_results:
    if "compare" in r.get('test_id', '').lower() or "比較" in r['query']:
        r_query_norm = normalize_query(r['query'])
        print(f"JSON test_id: {r['test_id']}")
        print(f"JSON query: {r['query']}")
        print(f"JSON query normalized: {r_query_norm}")
        print(f"Matched: {q_csv_norm in r_query_norm or r_query_norm in q_csv_norm}")
        print("-" * 50)
