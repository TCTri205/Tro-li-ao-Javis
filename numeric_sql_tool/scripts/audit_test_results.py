import sys
import pandas as pd
import numpy as np
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    pass

# Paths
GROUND_TRUTH_PATH = Path("eval/combined_200_testcases_ja.csv")
ACTUAL_RESULTS_XLSX = Path("db/numeric_sql_testcases_200_ja.xlsx")
ACTUAL_RESULTS_CSV = Path("db/numeric_sql_testcases_200_ja.csv")

from eval_utils import is_semantically_match

def audit():
    print("--- Bắt đầu đối soát trung thực ---")
    
    # 1. Load Ground Truth
    print(f"Loading Ground Truth from {GROUND_TRUTH_PATH}...")
    df_gt = pd.read_csv(GROUND_TRUTH_PATH)
    df_gt.columns = [c.lower() for c in df_gt.columns]
    
    # 2. Load Actual Results
    print(f"Loading Actual Results from {ACTUAL_RESULTS_XLSX}...")
    df_actual = pd.read_excel(ACTUAL_RESULTS_XLSX)
    df_actual.columns = [c.lower() for c in df_actual.columns]
    
    results = []
    correct = 0
    wrong = 0
    
    for idx in range(len(df_gt)):
        row_gt = df_gt.iloc[idx]
        row_actual = df_actual.iloc[idx]
        
        gt_sql = str(row_gt['sql'])
        actual_sql = str(row_actual['sql'])
        
        is_match = is_semantically_match(gt_sql, actual_sql)
        
        if is_match:
            correct += 1
            results.append({
                "question": row_gt['question'],
                "status": "PASS",
                "gt": row_gt['sql'],
                "actual": row_actual['sql'],
                "reason": ""
            })
        else:
            wrong += 1
            reason = "SQL Mismatch"
            if "skip" in gt_sql.lower() and "skip" not in actual_sql.lower():
                reason = "Should be SKIP (Ground Truth says so)"
            elif "skip" not in gt_sql.lower() and "skip" in actual_sql.lower():
                reason = "Should be SQL (Ground Truth has SQL)"
                
            results.append({
                "question": row_gt['question'],
                "status": "FAIL",
                "gt": row_gt['sql'],
                "actual": row_actual['sql'],
                "reason": reason
            })
            
    print(f"KẾT QUẢ THỰC TẾ: Đúng {correct}, Sai {wrong}")
    print(f"Độ chính xác thực tế: {(correct/len(df_gt))*100:.2f}%")
    
    # 5. Write Honest Report
    report_path = Path("eval/audit_report_200.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# BÁO CÁO ĐỐI SOÁT TRUNG THỰC (Audit Report)\n\n")
        f.write(f"- **File Ground Truth**: `{GROUND_TRUTH_PATH}`\n")
        f.write(f"- **File Kết quả Pipeline**: `{ACTUAL_RESULTS_XLSX}`\n")
        f.write(f"- **Tổng số case đối chiếu**: {len(df_gt)}\n")
        f.write(f"- **Số lượng ĐÚNG**: {correct}\n")
        f.write(f"- **Số lượng SAI**: {wrong}\n")
        f.write(f"- **Tỷ lệ chính xác thực tế**: {(correct/len(df_gt))*100:.2f}%\n\n")
        
        f.write("## Danh sách các case SAI (Discrepancies)\n\n")
        f.write("| Câu hỏi | SQL Ground Truth | SQL Thực tế sinh ra | Lý do |\n")
        f.write("|---|---|---|---|\n")
        
        for r in results:
            if r["status"] == "FAIL":
                f.write(f"| {r['question']} | `{r['gt']}` | `{r['actual']}` | {r['reason']} |\n")

    print(f"Báo cáo đối soát đã được ghi vào: {report_path}")

if __name__ == "__main__":
    audit()
