import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

actual = pd.read_excel(ROOT / 'db/random_100_results.xlsx')
gt = pd.read_csv(ROOT / 'eval/random_100_testcases_ja.csv')

merged = pd.merge(gt, actual, on='question', how='left')
merged['correct'] = merged['sql_x'].str.strip().str.lower() == merged['sql_y'].str.strip().str.lower()

# Normalize comparison helper
def normalize_sql(sql):
    if not sql or pd.isna(sql):
        return ""
    s = str(sql).strip().lower()
    if "skip" in s:
        return "skip"
    s = " ".join(s.split())
    import re
    s = s.replace("\n", " ").replace("\r", " ").replace(r"\|", "|")
    for char in [',', '(', ')', '=', '<', '>', '!', '+', '-', '*', '/', '|', ':', '.']:
        s = re.sub(rf'\s*\{char}\s*', char, s)
    return s.strip()

merged['correct_norm'] = merged.apply(lambda r: normalize_sql(r['sql_x']) == normalize_sql(r['sql_y']), axis=1)

failures = merged[~merged['correct_norm']]

lines = []
lines.append(f"Total: {len(merged)}")
lines.append(f"Correct: {merged['correct_norm'].sum()}")
lines.append(f"Failed: {len(failures)}")
lines.append("")
lines.append("=== FAILURE LIST ===")
for _, r in failures.iterrows():
    lines.append(f"Question: {r['question']}")
    lines.append(f"  GT:     {r['sql_x']}")
    lines.append(f"  Actual: {r['sql_y']}")
    lines.append("")

out_path = ROOT / 'eval/random_100_failure_report.txt'
with open(out_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f"Wrote failures to {out_path}")
