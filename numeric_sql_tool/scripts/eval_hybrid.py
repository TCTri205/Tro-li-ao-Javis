import sys
import asyncio
from pathlib import Path
import pandas as pd
from datetime import date
import logging
import time

# Reconfigure stdout/stderr to use UTF-8 encoding to prevent UnicodeEncodeError on Windows console
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    pass

# Set up logging to avoid spam but show warnings
logging.basicConfig(level=logging.WARNING)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from numeric_sql_tool.config import Settings
from numeric_sql_tool.db_utils import create_pool
from numeric_sql_tool.groq_client import GroqClient
from numeric_sql_tool.pipeline import run_numeric_pipeline

csv_path = ROOT / "eval" / "numeric_sql_testcases_ja.csv"
report_path = ROOT / "eval" / "evaluation_report_hybrid.md"

def sql_structure_key(sql: str) -> dict:
    s = sql.lower().strip()
    return {
        "has_group_by": "group by" in s,
        "has_count": "count(" in s,
        "has_sum": "coalesce(sum" in s,
        "has_avg": "coalesce(avg" in s,
        "is_skip": "skip" in s,
        "group_target": (
            "t.meeting_date" if "group by t.meeting_date" in s
            else "x.speaker" if "group by x.speaker" in s
            else "t.user_id" if "group by t.user_id" in s
            else "none"
        ),
    }

def sql_semantically_equal(sql_a: str, sql_b: str) -> bool:
    def clean(val):
        if not val or pd.isna(val):
            return ""
        return " ".join(str(val).lower().split())
    
    clean_a = clean(sql_a)
    clean_b = clean(sql_b)
    
    if clean_a == clean_b:
        return True
        
    # If both are skips, they are semantically equal
    if "skip" in clean_a and "skip" in clean_b:
        return True
        
    # If only one is skip, they are not equal
    if "skip" in clean_a or "skip" in clean_b:
        return False
        
    return sql_structure_key(sql_a) == sql_structure_key(sql_b)

async def main():
    settings = Settings.from_env()
    
    # 1. Setup Groq Client
    if not settings.groq_api_keys:
        print("Error: No Groq API keys found in env!")
        sys.exit(1)
    
    print(f"Loaded {len(settings.groq_api_keys)} Groq API keys.")
    llm_client = GroqClient(api_keys=settings.groq_api_keys, model=settings.groq_model)
    
    # 2. Setup PostgreSQL connection pool
    if not settings.database_url:
        print("Error: NUMERIC_SQL_DATABASE_URL not found!")
        sys.exit(1)
        
    print(f"Connecting to database at {settings.database_url}...")
    pool = await create_pool(settings.database_url)
    
    # 3. Read testcases
    print(f"Loading testcases from {csv_path}...")
    df = pd.read_csv(csv_path)
    
    ref_date = date(2026, 5, 28)
    user_id = "00000000-0000-0000-0000-000000000000"
    
    results = []
    correct_count = 0
    incorrect_count = 0
    
    print(f"Starting execution of {len(df)} test cases...")
    
    # Run sequentially with a small delay to respect rate limits
    for idx, row in df.iterrows():
        row_num = idx + 2  # 1-indexed, header is row 1
        question = str(row['question']).strip()
        expected_sql = str(row['SQL']).strip()
        csv_eval = str(row.get('Đánh giá', '')).strip()
        
        print(f"[{idx+1}/{len(df)}] Row {row_num}: {question[:40]}...")
        
        # Execute pipeline in hybrid mode
        try:
            start_time = time.time()
            result = await run_numeric_pipeline(
                question=question,
                db_pool=pool,
                llm_client=llm_client,
                user_id=user_id,
                reference_date=ref_date,
                statement_timeout_ms=settings.statement_timeout_ms
            )
            elapsed = time.time() - start_time
            
            # Format actual SQL
            sql_used = result.metadata.get("sql")
            if sql_used:
                actual_sql = str(sql_used)
            elif result.metadata.get("skipped"):
                actual_sql = f"SKIP (operator={result.operator}, target={result.target})"
            else:
                actual_sql = "SKIP (no SQL)"
                
            # Database results summary
            db_res = []
            if result.rows:
                for r in result.rows:
                    if r.group_key:
                        db_res.append(f"{r.group_key}: {r.value}")
                    else:
                        db_res.append(f"{r.value}")
            db_res_str = ", ".join(db_res) if db_res else "No data"
            error_str = ""
            
        except Exception as exc:
            elapsed = 0.0
            actual_sql = f"ERROR: {exc}"
            db_res_str = "N/A"
            error_str = str(exc)
            
        # Compare
        is_wrong = not sql_semantically_equal(expected_sql, actual_sql)
        
        reason = ""
        if is_wrong:
            incorrect_count += 1
            if "skip" in expected_sql.lower() and "skip" not in actual_sql.lower():
                reason = "Should have skipped (qualitative/semantic question) but generated SQL instead"
            elif "skip" not in expected_sql.lower() and "skip" in actual_sql.lower():
                reason = "Should have generated SQL (quantitative/count question) but skipped instead"
            else:
                reason = "SQL structure / condition mismatch"
        else:
            correct_count += 1
            
        results.append({
            "row": row_num,
            "question": question,
            "expected_sql": expected_sql,
            "actual_sql": actual_sql,
            "db_res": db_res_str,
            "is_wrong": is_wrong,
            "reason": reason,
            "elapsed": elapsed,
            "error": error_str
        })
        
        # Pause slightly to avoid Groq rate limit spikes (1.2s delay as configured in CLI batch)
        await asyncio.sleep(1.2)
        
    await pool.close()
    
    # 4. Generate Markdown report
    accuracy = (correct_count / len(df)) * 100 if len(df) > 0 else 0
    print(f"Done! Correct: {correct_count}, Incorrect: {incorrect_count}, Accuracy: {accuracy:.2f}%")
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Báo cáo Đánh giá chi tiết (Hybrid Mode - 200 Test Cases)\n\n")
        f.write("Báo cáo đánh giá hiệu năng chạy thực tế trên toàn bộ 200 test cases tiếng Nhật sử dụng mô hình Hybrid (Groq Llama-3 + Heuristics fallback) kết hợp thực thi trên cơ sở dữ liệu.\n\n")
        
        f.write("## Tóm tắt kết quả\n")
        f.write(f"- **Tổng số test cases**: {len(df)}\n")
        f.write(f"- **Số lượng Đúng (Semantically Matches)**: {correct_count} ({accuracy:.2f}%)\n")
        f.write(f"- **Số lượng Sai/Không khớp**: {incorrect_count} ({100-accuracy:.2f}%)\n\n")
        
        f.write("## Chi tiết đối chiếu các Test Case\n\n")
        f.write("| Dòng | Câu hỏi | SQL mong muốn (Expected) | SQL sinh ra (Hybrid Model) | Kết quả DB | Kết quả đối chiếu |\n")
        f.write("|---|---|---|---|---|---|\n")
        
        for r in results:
            q_esc = r["question"].replace("\n", " <br> ")
            exp_esc = r["expected_sql"].replace("\n", " <br> ").replace("|", "\\|")
            act_esc = r["actual_sql"].replace("\n", " <br> ").replace("|", "\\|")
            db_res_esc = r["db_res"].replace("\n", " <br> ").replace("|", "\\|")
            
            if r["is_wrong"]:
                status = f"🔴 **Sai**<br>Lý do: {r['reason']}"
                if r["error"]:
                    status += f"<br>Error: `{r['error']}`"
            else:
                status = "🟢 **Đúng**"
                
            f.write(f"| {r['row']} | {q_esc} | `{exp_esc}` | `{act_esc}` | {db_res_esc} | {status} |\n")
            
    print(f"Report written to {report_path}")

if __name__ == "__main__":
    asyncio.run(main())
