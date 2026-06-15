import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import argparse

def main():
    parser = argparse.ArgumentParser(description="Analyze regression failures")
    parser.add_argument("--actual", type=Path, default=ROOT / 'db/numeric_sql_testcases_300_ja.xlsx', help="Pipeline output Excel file")
    parser.add_argument("--gt", type=Path, default=ROOT / 'eval/combined_300_testcases_ja.csv', help="Ground Truth CSV file")
    parser.add_argument("--out", type=Path, default=ROOT / 'eval/regression_failures_report.txt', help="Output failure report file")
    args = parser.parse_args()

    actual = pd.read_excel(args.actual)
    gt = pd.read_csv(args.gt)

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

    merged = pd.merge(gt, actual, on='question', how='left')
    merged['correct_norm'] = merged.apply(lambda r: normalize_sql(r['sql_x']) == normalize_sql(r['sql_y']), axis=1)

    failures = merged[~merged['correct_norm']]

    lines = []
    lines.append(f"Failed count: {len(failures)}")
    for idx, r in failures.iterrows():
        lines.append(f"Q: {r['question']}")
        lines.append(f"  GT:     {r['sql_x']}")
        lines.append(f"  Actual: {r['sql_y']}")
        lines.append("")

    with open(args.out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"Wrote failures to {args.out}")

if __name__ == "__main__":
    main()
