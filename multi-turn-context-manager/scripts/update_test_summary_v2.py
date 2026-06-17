import json
import csv
import os

# Paths
V1_JSON = r'd:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/test_results_v1.json'
V2_JSON = r'd:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/test_results_v2.json'
CSV_PATH = r'd:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/reports/tests/test_summary.csv'

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def update_csv():
    v1_results = load_json(V1_JSON)
    v2_results = load_json(V2_JSON)
    
    rows = []
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            rows.append(row)

    # Mapping
    mapping = {
        'V1_STD_MULTI_TURN': ['SCENARIO_1_T1', 'SCENARIO_1_T2', 'SCENARIO_2_T3', 'SCENARIO_4_T4'],
        'V1_NEG_AMBIG_ENTITY': ['NEG_001'],
        'V1_NEG_TOPIC_SHIFT': ['NEG_002'],
        'V1_NEG_NEW_CONV': ['NEG_003'],
        'V1_NEG_TIMEOUT': ['NEG_004'],
        'V1_NEG_BAD_JSON': ['NEG_005'],
        'V1_NEG_DIRTY_TYPO': ['NEG_006'],
        'V1_NEG_CODE_MIXING': ['NEG_007'],
        'V1_NEG_COMPARE': ['NEG_008'],
        'V1_NEG_LRU_EVICTION': ['NEG_009'],
        'V1_NEG_TTL_EXPIRED': ['NEG_010'],
        'V1_NEG_ENTITY_QUICK': ['NEG_013'],
        'V1_FIX_EMBED_FAIL': ['FIX_001'],
        'V1_FIX_SPACES': ['FIX_002'],
        'V1_FIX_HALLUCINATION': ['FIX_005'],
        'V1_FIX_INTEGRITY': ['FIX_008', 'FIX_009'],
        'V2_STD_MULTI_TURN': ['STD_TURN_1', 'STD_TURN_2_FOLLOWUP', 'STD_TURN_3_SWITCH', 'STD_TURN_4_SWITCHBACK'],
        'V2_RAG_DEEP': ['RAG_DEEP_INQUIRY', 'FOLLOW_UP_STATE'],
        'V2_CROSS_DOC_REASONING': ['CROSS_DOC_REASONING'],
        'V2_SQL_AGGREGATION': ['SUM_DURATION', 'MAX_DURATION'],
        'V2_ENTITY_MEMORY': ['ENTITY_COMPARISON'],
        'V2_NEG_AMBIG_ENTITY': ['NEG_001_AMBIGUOUS_ENTITY'],
        'V2_FIX_LOCK_TIMEOUT': ['FIX_009_LOCK_TIMEOUT'],
        'V2_STRESS_PARALLEL': ['CONCURRENT_5_REQS']
    }

    results_map_v1 = {r['test_id']: r for r in v1_results}
    results_map_v2 = {r['test_id']: r for r in v2_results}

    for row in rows:
        ver = row['Version']
        sid = row['Scenario ID']
        res_map = results_map_v1 if ver == 'V1' else results_map_v2
        
        tids = mapping.get(sid, [])
        matched = [res_map[tid] for tid in tids if tid in res_map]
        
        if matched:
            all_passed = all(m['passed'] for m in matched)
            row['Status'] = 'PASS' if all_passed else 'FAIL'
            
            answers = []
            for i, tid in enumerate(tids):
                if tid in res_map:
                    ans = res_map[tid]['answer'].replace('\n', ' ').strip()
                    answers.append(f"T{i+1}: {ans}")
                else:
                    answers.append(f"T{i+1}: [MISSING]")
            row['Actual Result (Captured Answer)'] = ' | '.join(answers)

    with open(CSV_PATH, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

if __name__ == '__main__':
    update_csv()
    print("CSV updated with latest JSON data.")
