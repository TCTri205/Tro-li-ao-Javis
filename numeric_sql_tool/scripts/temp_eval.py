import sys
import argparse
import asyncio
from pathlib import Path
import pandas as pd
from datetime import date
from typing import Any

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eval_utils import is_semantically_match
from numeric_sql_tool.config import Settings, require_database_url
from numeric_sql_tool.db_utils import create_pool
from numeric_sql_tool.pipeline import run_numeric_pipeline

DEFAULT_REFERENCE_DATE = date(2026, 5, 28)
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000000"

def _sql_from_result(result) -> str:
    sql = result.metadata.get("sql")
    if sql:
        return str(sql)
    if result.metadata.get("skipped"):
        err = result.metadata.get("error", "")
        return f"SKIP (operator={result.operator}, target={result.target}) {err}".strip()
    return "SKIP (no SQL)"

def format_query_result(result) -> str:
    if result.metadata.get("skipped"):
        return "-"
    if not result.rows:
        return "No data (0.0)"
    
    # If there is only 1 row and no group_key, format the value
    if len(result.rows) == 1 and (result.rows[0].group_key is None or result.rows[0].group_key == "none"):
        val = result.rows[0].value
        # Check if it has metadata like meeting_date
        meta = result.rows[0].metadata
        if meta and "meeting_date" in meta:
            return f"{val} ({meta['meeting_date']})"
        return f"{val}"
    
    # If it's grouped, format as group_key: value
    formatted_groups = []
    for row in result.rows:
        key = row.group_key or "unknown"
        val = row.value
        formatted_groups.append(f"{key}: {val}")
    return ", ".join(formatted_groups)

async def evaluate_async(actual_path: Path, gt_path: Path, report_path: Path):
    print(f"Evaluating Actual: {actual_path}")
    print(f"Against Ground Truth: {gt_path}")
    
    # Load ground truth file
    df_gt = pd.read_csv(gt_path)
    df_gt.columns = [c.lower() for c in df_gt.columns]
    
    # Connect to PostgreSQL
    settings = Settings.from_env()
    db_url = require_database_url(settings.database_url)
    pool = await create_pool(db_url)
    
    results = []
    correct_count = 0
    incorrect_count = 0
    
    sem = asyncio.Semaphore(10)  # limit concurrency
    
    async def process_one(idx: int, row_gt: Any) -> dict[str, Any]:
        nonlocal correct_count, incorrect_count
        q = row_gt['question']
        gt_sql = str(row_gt['sql'])
        
        async with sem:
            try:
                result = await run_numeric_pipeline(
                    question=q,
                    db_pool=pool,
                    llm_client=None, # regex-only
                    user_id=DEFAULT_USER_ID,
                    reference_date=DEFAULT_REFERENCE_DATE,
                )
                actual_sql = _sql_from_result(result)
                query_result_str = format_query_result(result)
            except Exception as exc:
                actual_sql = f"ERROR: {exc}"
                query_result_str = "ERROR"
        
        is_match = is_semantically_match(gt_sql, actual_sql)
        
        reason = ""
        if is_match:
            status = "🟢 **Đúng**"
        else:
            status = "🔴 **Sai**"
            if "skip" in gt_sql.lower() and "skip" not in actual_sql.lower():
                reason = "Ground Truth yêu cầu SKIP, nhưng Pipeline sinh SQL."
            elif "skip" not in gt_sql.lower() and "skip" in actual_sql.lower():
                reason = "Ground Truth yêu cầu SQL, nhưng Pipeline sinh SKIP."
            else:
                reason = "SQL không khớp về cấu trúc hoặc điều kiện lọc."
                
        return {
            "row": idx + 2,
            "question": q,
            "gt_sql": gt_sql,
            "actual_sql": actual_sql,
            "query_result": query_result_str,
            "status": status,
            "reason": reason,
            "is_match": is_match
        }

    # Run pipeline for all questions
    tasks = [process_one(idx, df_gt.iloc[idx]) for idx in range(len(df_gt))]
    results_raw = await asyncio.gather(*tasks)
    
    # Sort results by row index to match CSV order
    results_raw.sort(key=lambda x: x["row"])
    
    # Count results
    for r in results_raw:
        if r["is_match"]:
            correct_count += 1
        else:
            incorrect_count += 1
            
    await pool.close()
    
    # Write report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Báo cáo Đánh giá Trung thực (Honest Evaluation Report)\n\n")
        f.write(f"- **Ngày đánh giá**: {date.today().isoformat()}\n")
        f.write(f"- **Tổng số case**: {len(df_gt)}\n")
        f.write(f"- **Số lượng ĐÚNG**: {correct_count}\n")
        f.write(f"- **Số lượng SAI**: {incorrect_count}\n")
        f.write(f"- **Độ chính xác**: {(correct_count/len(df_gt))*100:.2f}%\n\n")
        
        f.write("## Chi tiết kết quả\n\n")
        f.write("| Dòng | Câu hỏi | SQL thực tế | Kết quả truy vấn | Cú pháp mong muốn | Kết quả |\n")
        f.write("|---|---|---|---|---|---|\n")
        
        for r in results_raw:
            q_esc = r["question"].replace("\n", " <br> ")
            act_esc = str(r["actual_sql"]).replace("\n", " <br> ").replace("|", "\\|")
            gt_esc = str(r["gt_sql"]).replace("\n", " <br> ").replace("|", "\\|")
            res_esc = str(r["query_result"]).replace("\n", " <br> ").replace("|", "\\|")
            
            status_str = r["status"]
            if r["reason"]:
                status_str += f"<br>*{r['reason']}*"
                
            f.write(f"| {r['row']} | {q_esc} | `{act_esc}` | {res_esc} | `{gt_esc}` | {status_str} |\n")

    print(f"Báo cáo đã được tạo tại: {report_path}")
    print(f"Tổng số case Đúng: {correct_count}, Sai: {incorrect_count}")

def main():
    parser = argparse.ArgumentParser(description="Honest evaluation of Pipeline results vs Ground Truth with DB execution")
    parser.add_argument("--actual", type=Path, default=ROOT / "db" / "numeric_sql_testcases_300_ja.xlsx", help="Pipeline output file")
    parser.add_argument("--gt", type=Path, default=ROOT / "eval" / "combined_300_testcases_ja.csv", help="Ground Truth CSV file")
    parser.add_argument("--out", type=Path, default=ROOT / "eval" / "evaluation_report_300_honest.md", help="Output report file")
    args = parser.parse_args()
    
    asyncio.run(evaluate_async(args.actual, args.gt, args.out))

if __name__ == "__main__":
    main()
