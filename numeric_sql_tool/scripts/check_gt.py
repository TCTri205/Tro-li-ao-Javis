import sys
from pathlib import Path
from datetime import date
import pandas as pd

# Add src to sys.path
sys.path.insert(0, str(Path("d:/VJ/Tro-li-ao-Javis/numeric_sql_tool/src")))

from numeric_sql_tool.heuristics import heuristic_numeric_intent
from numeric_sql_tool.pipeline import build_numeric_sql

def check_all():
    csv_path = Path("d:/VJ/Tro-li-ao-Javis/numeric_sql_tool/eval_v2/questions_GTqueries.csv")
    df = pd.read_csv(csv_path)
    
    mismatch_count = 0
    
    out_lines = []
    for idx, row in df.iterrows():
        question = row['question']
        gt_sql = row['SQL']
        
        intent = heuristic_numeric_intent(question)
        generated_sql = build_numeric_sql(intent)
        
        if generated_sql is None:
            expected_gt = "SKIP (operator=skip, target=none)"
        else:
            expected_gt = generated_sql
            
        # Standardize spaces for comparison
        gt_standardized = " ".join(str(gt_sql).strip().split())
        gen_standardized = " ".join(expected_gt.strip().split())
        
        # Strip outer quotes if any
        if gt_standardized.startswith('"') and gt_standardized.endswith('"'):
            gt_standardized = gt_standardized[1:-1].strip()
            gt_standardized = " ".join(gt_standardized.split())
            
        if gt_standardized != gen_standardized:
            mismatch_count += 1
            out_lines.append(f"Row {idx+2} | Q: {question}")
            out_lines.append(f"  GT:  {gt_sql}")
            out_lines.append(f"  GEN: {expected_gt}")
            out_lines.append("-" * 80)
            
    out_lines.append(f"Total mismatches: {mismatch_count} out of {len(df)} rows")
    Path("d:/VJ/Tro-li-ao-Javis/numeric_sql_tool/eval_v2/check_gt_report.txt").write_text("\n".join(out_lines), encoding="utf-8")
    print(f"Total mismatches: {mismatch_count} out of {len(df)} rows. Detailed report written to check_gt_report.txt.")

if __name__ == "__main__":
    check_all()
