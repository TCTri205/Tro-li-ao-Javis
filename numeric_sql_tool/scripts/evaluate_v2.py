import asyncio
import sys
from datetime import date
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path("d:/VJ/Tro-li-ao-Javis/numeric_sql_tool/src")))

from numeric_sql_tool.config import Settings, require_database_url
from numeric_sql_tool.db_utils import create_pool
from numeric_sql_tool.pipeline import run_numeric_pipeline
from numeric_sql_tool.heuristics import heuristic_numeric_intent

async def main():
    queries_file = Path("d:/VJ/Tro-li-ao-Javis/numeric_sql_tool/eval_v2/queries.txt")
    queries = [line.strip() for line in queries_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    
    settings = Settings.from_env()
    db_url = require_database_url(settings.database_url)
    pool = await create_pool(db_url)
    
    user_id = "00000000-0000-0000-0000-000000000000"
    ref_date = date(2026, 5, 28)
    
    print(f"Loaded {len(queries)} queries.")
    
    # We will write the output to a file so we can analyze it without encoding issues on standard out.
    output_lines = []
    
    try:
        for idx, q in enumerate(queries, 1):
            intent = heuristic_numeric_intent(q)
            # Run pipeline to get result (including execution and SQL)
            res = await run_numeric_pipeline(
                question=q,
                db_pool=pool,
                llm_client=None,
                user_id=user_id,
                reference_date=ref_date
            )
            output_lines.append(
                f"Row {idx} | Q: {q}\n"
                f"  Intent: operator={intent.operator}, target={intent.target}, speaker={intent.speaker}, keyword={intent.keyword}\n"
                f"  Result: operator={res.operator}, target={res.target}, rows_len={len(res.rows)}\n"
                f"  SQL: {res.metadata.get('sql')}\n"
            )
            
        output_file = Path("d:/VJ/Tro-li-ao-Javis/numeric_sql_tool/eval_v2/executed_print_all.txt")
        output_file.write_text("\n".join(output_lines), encoding="utf-8")
        print(f"Wrote results to {output_file}")
    finally:
        await pool.close()

if __name__ == "__main__":
    asyncio.run(main())
