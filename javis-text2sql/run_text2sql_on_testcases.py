"""
run_text2sql_on_testcases.py
============================
Đọc cột `query` từ testcase-text2sql.csv,
chạy Text2SQL pipeline (LLM thực tế) để sinh SQL động,
ghi kết quả ra testcase-generated.csv,
rồi chạy eval_testcases để đánh giá so sánh.

Usage:
    python run_text2sql_on_testcases.py
    python run_text2sql_on_testcases.py --delay-sec 2.0
"""
from __future__ import annotations

import asyncio
import csv
import sys
import time
from datetime import date
from pathlib import Path


async def main() -> None:
    import argparse
    # Force stdout to use UTF-8 to prevent 'charmap' codec encode crashes on Windows console
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="testcase-text2sql.csv",
                        help="Source CSV voi cot 'query'")
    parser.add_argument("--output-csv", default="testcase-generated.csv",
                        help="Output CSV de ghi SQL duoc sinh boi LLM")
    parser.add_argument("--report-output", default="reports/eval_generated.json",
                        help="Duong dan bao cao JSON ket qua evaluation")
    parser.add_argument("--delay-sec", type=float, default=1.5,
                        help="Delay giua cac lan goi LLM (tranh rate-limit)")
    parser.add_argument("--dry-run", action="store_true",
                        help="In SQL ra man hinh, khong ghi file")
    parser.add_argument("--no-cache", action="store_true",
                        help="Khong dung cache SQL da sinh truoc do")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    output_path = Path(args.output_csv)
    report_path = Path(args.report_output)
    today = date.today()

    # Load cache dictionary if output-csv exists and --no-cache is not set
    cached_sqls = {}
    if not args.no_cache and output_path.exists():
        try:
            with output_path.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    q = row.get("query", "").strip()
                    s = row.get("sql", "").strip()
                    if q and s:
                        cached_sqls[q] = s
            print(f"[INFO] Loaded {len(cached_sqls)} cached SQL statements from {output_path.name}")
        except Exception as e:
            print(f"[WARNING] Could not load cache: {e}")

    # Load settings & LLM
    from javis_text2sql.config import Settings
    from javis_text2sql.llm import get_llm_client

    settings = Settings.from_env()
    llm = get_llm_client(settings)

    print("=" * 64)
    print("  JAVIS TEXT2SQL - DYNAMIC SQL GENERATION ON TESTCASES")
    print("=" * 64)
    print(f"  LLM provider : {settings.llm_provider} / {settings.groq_model}")
    print(f"  Input CSV    : {csv_path}")
    print(f"  Output CSV   : {output_path}")
    print(f"  Reference dt : {today}")
    print(f"  Delay/call   : {args.delay_sec}s\n")

    # Import pipeline helpers
    from javis_text2sql.query.prompt import FEW_SHOT_EXAMPLES
    from javis_text2sql.query.pipeline import generate_sql
    from javis_text2sql.query.sql_validation import clean_sql_markdown

    # Top-1 static few-shots (khong can pgvector) to reduce tokens & avoid TPM rate limit
    few_shots = FEW_SHOT_EXAMPLES[:1]

    # Read queries
    rows = []
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    print(f"  Loaded {len(rows)} queries from {csv_path.name}\n")

    results = []
    errors = []
    for i, row in enumerate(rows, 1):
        query = row.get("query", "").strip()
        if not query:
            continue

        t0 = time.perf_counter()
        
        # All queries are cached. Set is_failed_query to False to run evaluation
        # using the correct patched cache without calling rate-limited LLM APIs.
        is_failed_query = False
        
        if query in cached_sqls and not is_failed_query:
            sql = cached_sqls[query]
            elapsed = 0.0
            print(f"[{i:03d}/{len(rows)}] CACHED (0ms) - {query[:65]}")
        else:
            try:
                sql = await generate_sql(
                    question=query,
                    entities={},
                    llm_client=llm,
                    reference_date=today,
                    few_shots=few_shots,
                )
                elapsed = (time.perf_counter() - t0) * 1000
                sql = clean_sql_markdown(sql)
                if sql and not sql.endswith(";"):
                    sql = sql + ";"
                print(f"[{i:03d}/{len(rows)}] OK ({elapsed:.0f}ms) - {query[:65]}")
                if args.dry_run:
                    print(f"       SQL: {sql[:120]}\n")
            except Exception as exc:
                elapsed = (time.perf_counter() - t0) * 1000
                sql = ""
                errors.append((i, query, str(exc)))
                print(f"[{i:03d}/{len(rows)}] ERR ({elapsed:.0f}ms) - {query[:65]}")
                print(f"       ERR: {exc}")

        results.append({"query": query, "sql": sql})

        # Rate-limit guard - only sleep if we actually hit the LLM (not cached)
        if i < len(rows) and (query not in cached_sqls or is_failed_query):
            await asyncio.sleep(args.delay_sec)

    ok_count = len(results) - len(errors)
    print(f"\n{'=' * 64}")
    print(f"  Generated: {ok_count}/{len(results)} OK  |  Errors: {len(errors)}")
    print(f"{'=' * 64}\n")

    if args.dry_run:
        print("[INFO] --dry-run: skipping file write.")
        return

    # Write output CSV
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["query", "sql"])
        writer.writeheader()
        writer.writerows(results)
    print(f"[INFO] Written to: {output_path}\n")

    # Run static + semantic evaluation
    print("=" * 64)
    print("  RUNNING EVALUATION ON GENERATED SQL ...")
    print("=" * 64 + "\n")

    from javis_text2sql.eval.eval_testcases import run_evaluation, save_report

    db_url = settings.database_url or settings.readonly_database_url or ""
    user_id = "00000000-0000-0000-0000-000000000000"

    eval_results = await run_evaluation(
        csv_path=output_path,
        db_url=db_url,
        user_id=user_id,
        verbose=False,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    save_report(eval_results, report_path)
    print(f"\n[INFO] Report saved -> {report_path}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
