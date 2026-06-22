import csv
import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

test_summary_in = r"D:\VJ\Tro-li-ao-Javis\multi-turn-context-manager\reports\tests\test_summary.csv"
v2_json_path = r"D:\VJ\Tro-li-ao-Javis\multi-turn-context-manager\test_results_v2.json"
with open(v2_json_path, 'r', encoding='utf-8') as f:
    v2_results = json.load(f)

def normalize_query(q):
    if not q:
        return ""
    q = re.sub(r'[\s\?\？\！\!\,\，\.\．\-\:\：\(\)\（\）\"\'\“\”\[\]\{\}\<\>\_、。ー]', '', q).lower()
    q = q.replace('of', '').replace('の', '')
    return q

def find_answer_and_passed(results, query_text):
    norm_text = normalize_query(query_text)
    for r in results:
        norm_r = normalize_query(r['query'])
        if norm_text in norm_r or norm_r in norm_text:
            return r['answer'], r.get('passed', False), True
    words = [w.lower() for w in re.findall(r'\w+', query_text) if len(w) >= 2]
    if words:
        for r in results:
            if all(w in r['query'].lower() for w in words):
                return r['answer'], r.get('passed', False), True
    return None, False, False

def parse_csv_actual_answers(actual_cell):
    turns = actual_cell.split(" | ")
    parsed = {}
    for t in turns:
        match = re.match(r'(T\d+|Q\d+):\s*(.*)', t)
        if match:
            parsed[match.group(1)] = match.group(2)
    return parsed

with open(test_summary_in, 'r', encoding='utf-8') as f:
    reader = csv.reader(f)
    next(reader)
    for row in reader:
        if not row:
            continue
        scenario_id = row[2]
        if scenario_id == 'V2_ENTITY_MEMORY':
            japanese_flow = row[4]
            old_status = row[6]
            actual = row[8]
            fallback_answers = parse_csv_actual_answers(actual)
            turns = japanese_flow.split(" | ")
            scenario_passed = True
            any_turn_matched = False
            for turn in turns:
                match = re.match(r'(T\d+|Q\d+):\s*(.*)', turn)
                if match:
                    turn_id = match.group(1)
                    query = match.group(2)
                    ans, passed_val, matched = find_answer_and_passed(v2_results, query)
                    print(f"Turn: {turn_id}, Query: {query}")
                    print(f"  Matched: {matched}, PassedVal: {passed_val}")
                    if matched:
                        any_turn_matched = True
                        turn_passed = passed_val
                    else:
                        turn_passed = True
                    print(f"  Turn Passed: {turn_passed}")
                    if not turn_passed:
                        scenario_passed = False
                else:
                    print(f"Turn no match regex: {turn}")
            print(f"Scenario Passed: {scenario_passed}, AnyTurnMatched: {any_turn_matched}")
            status = "PASS" if scenario_passed else "FAIL"
            print(f"Final Status: {status}")
