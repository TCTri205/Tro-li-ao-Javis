import json
import csv
import os

# Paths
V1_JSON = r'd:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/test_results_v1.json'
V2_JSON = r'd:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/test_results_v2.json'
CSV_PATH = r'd:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/reports/tests/test_summary.csv'

def check_integrity():
    with open(V1_JSON, 'r', encoding='utf-8') as f:
        v1 = json.load(f)
    with open(V2_JSON, 'r', encoding='utf-8') as f:
        v2 = json.load(f)
        
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    issues = []
    
    # Mapping for verification
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

    for row in rows:
        sid = row['Scenario ID']
        ver = row['Version']
        results = v1 if ver == 'V1' else v2
        
        tids = mapping.get(sid, [])
        matched = [r for r in results if r['test_id'] in tids]
        
        if not matched:
            issues.append(f"No match for {sid} ({ver})")
            continue
            
        # Verify Status
        expected_status = 'PASS' if all(m['passed'] for m in matched) else 'FAIL'
        if row['Status'] != expected_status:
            issues.append(f"Status mismatch for {sid}: expected {expected_status}, got {row['Status']}")
            
        # Verify Answer Count
        actual_ans = row['Actual Result (Captured Answer)']
        turn_count = len(actual_ans.split(' | '))
        if turn_count != len(matched):
            issues.append(f"Turn count mismatch for {sid}: expected {len(matched)}, got {turn_count}")

    if not issues:
        print("Integrity Check: PASSED")
    else:
        print("Integrity Check: FAILED")
        for issue in issues:
            print(f"  - {issue}")

if __name__ == '__main__':
    check_integrity()
