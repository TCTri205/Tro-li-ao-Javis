import asyncio
import csv
import sys
from datetime import date
from pathlib import Path

# Add src to sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

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

async def main():
    queries_file = ROOT / "eval_v2" / "queries.txt"
    queries = [line.strip() for line in queries_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    
    settings = Settings.from_env()
    db_url = require_database_url(settings.database_url)
    pool = await create_pool(db_url)
    
    output_rows = []
    print(f"Loaded {len(queries)} queries. Starting evaluation...")
    
    try:
        for idx, q in enumerate(queries, 1):
            try:
                res = await run_numeric_pipeline(
                    question=q,
                    db_pool=pool,
                    llm_client=None, # regex-heuristics only
                    user_id=DEFAULT_USER_ID,
                    reference_date=DEFAULT_REFERENCE_DATE
                )
                sql_str = _sql_from_result(res)
                result_str = format_query_result(res)
            except Exception as e:
                sql_str = f"ERROR: {str(e)}"
                result_str = "ERROR"
            
            output_rows.append({
                "question": q,
                "sql": sql_str,
                "query_result": result_str
            })
            if idx % 50 == 0 or idx == len(queries):
                print(f"Evaluated {idx}/{len(queries)} queries...")
                
        output_file = ROOT / "eval_v2" / "query_results_new.csv"
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["question", "sql", "query_result"], quoting=csv.QUOTE_MINIMAL)
            writer.writeheader()
            writer.writerows(output_rows)
            
        print(f"Successfully wrote {len(output_rows)} rows to {output_file}")
        
    finally:
        await pool.close()

if __name__ == "__main__":
    asyncio.run(main())
