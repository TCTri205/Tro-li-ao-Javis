import pandas as pd
import sys

# Doc ket qua pipeline
actual = pd.read_excel('db/stress_100_results.xlsx')
gt = pd.read_csv('eval/stress_100_testcases_ja.csv')

# Merge
merged = pd.merge(gt, actual, on='question', how='left')
merged['correct'] = merged['sql_x'].str.strip() == merged['sql_y'].str.strip()
merged['actual_sql'] = merged['sql_y']

lines = []
lines.append('=== ACCURACY BY CATEGORY ===')
for cat, grp in merged.groupby('category'):
    n = len(grp)
    correct = grp['correct'].sum()
    pct = 100 * correct / n
    lines.append(f'{cat:25s}: {correct}/{n} correct ({pct:.0f}%)')

lines.append('')
lines.append('=== TOTAL ===')
total = len(merged)
total_correct = merged['correct'].sum()
lines.append(f'Total: {total_correct}/{total} correct ({100*total_correct/total:.0f}%)')

lines.append('')
lines.append('=== FAILURES (cac cau bi sai) ===')
failures = merged[~merged['correct']]
for _, row in failures.iterrows():
    lines.append(f'[{row["category"]}] {row["question"]}')
    lines.append(f'  Actual SQL: {str(row["actual_sql"])[:120]}')
    lines.append('')

out_path = 'eval/stress_100_failure_report.txt'
with open(out_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print(f'Saved failure report to {out_path}')
print('\n'.join(lines[:15]))

