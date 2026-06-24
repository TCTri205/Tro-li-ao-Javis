import json
import sys

# Reconfigure stdout to support UTF-8 on Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

with open("test_results_v1.json", "r", encoding="utf-8") as f:
    results = json.load(f)

for r in results:
    if r["test_id"] == "SCENARIO_1_T2":
        print(json.dumps(r, ensure_ascii=False, indent=2))
