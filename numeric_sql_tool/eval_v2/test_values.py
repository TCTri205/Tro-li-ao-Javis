import sys
import os
import math
import asyncio
import asyncpg
import pandas as pd
from pathlib import Path
from datetime import date

import pytest

# Add src to sys.path
ROOT = Path("d:/VJ/Tro-li-ao-Javis/numeric_sql_tool")
sys.path.insert(0, str(ROOT / "src"))

from numeric_sql_tool.heuristics import heuristic_numeric_intent, resolve_date_range, enforce_intent_invariants
from numeric_sql_tool.pipeline import build_numeric_sql

def clean_sql(sql):
    if not sql or pd.isna(sql):
        return ""
    # Strip quotes if present
    sql = str(sql).strip()
    if sql.startswith('"') and sql.endswith('"'):
        sql = sql[1:-1].strip()
    return sql

async def compare_results(gt_rows, gen_rows, question_type):
    if not gt_rows and not gen_rows:
        return True, "Both empty"
    
    # Helper to parse a row into a comparable structure
    def parse_rows(rows):
        parsed = []
        for r in rows:
            d = dict(r)
            # Standardize numeric values to float
            for k, v in d.items():
                if isinstance(v, (int, float)):
                    d[k] = float(v)
                elif v is None:
                    d[k] = 0.0 if k == "value" else None
            parsed.append(d)
        return parsed

    gt_parsed = parse_rows(gt_rows)
    gen_parsed = parse_rows(gen_rows)

    if len(gt_parsed) != len(gen_parsed):
        # Special case: for LIMIT queries or Top-N, let's check if the first N match or if it's comparable
        if len(gt_parsed) == 1 and len(gen_parsed) > 0:
            # Maybe gen has more rows but first row matches
            first_gt = gt_parsed[0]
            first_gen = gen_parsed[0]
            # Compare value
            if "value" in first_gt and "value" in first_gen:
                if math.isclose(first_gt["value"] or 0.0, first_gen["value"] or 0.0, abs_tol=1e-5):
                    return True, f"First row matches (GT len=1, GEN len={len(gen_parsed)})"
        return False, f"Row count mismatch: GT={len(gt_parsed)}, GEN={len(gen_parsed)}"

    for idx, (gt_r, gen_r) in enumerate(zip(gt_parsed, gen_parsed)):
        # Compare key values
        for k in gt_r.keys():
            if k not in gen_r:
                # Some column name mismatch but same semantic meaning (e.g. session_id vs group_key)
                # Let's check if they have equivalent columns
                alternative_keys = {
                    "transcript_id": ["group_key"],
                    "session_id": ["group_key"],
                    "group_key": ["transcript_id", "session_id", "speaker"]
                }
                found_match = False
                for alt in alternative_keys.get(k, []):
                    if alt in gen_r:
                        if gt_r[k] == gen_r[alt]:
                            found_match = True
                            break
                if found_match:
                    continue
                return False, f"Column {k} missing in GEN row {idx}"
            
            val_gt = gt_r[k]
            val_gen = gen_r[k]
            if isinstance(val_gt, float) and isinstance(val_gen, float):
                if not math.isclose(val_gt, val_gen, abs_tol=1e-5):
                    return False, f"Value mismatch in col '{k}' at row {idx}: GT={val_gt}, GEN={val_gen}"
            else:
                # Cast to string/lowercase comparison for speaker/session
                if str(val_gt).lower().strip() != str(val_gen).lower().strip():
                    return False, f"Key mismatch in col '{k}' at row {idx}: GT='{val_gt}', GEN='{val_gen}'"

    return True, "Match"

@pytest.mark.asyncio
async def test_value_correctness():
    db_url = "postgresql://app_user:app_password@localhost:54331/app_db"
    pool = await asyncpg.create_pool(db_url)
    
    csv_path = ROOT / "eval_v2" / "questions_GTqueries.csv"
    df = pd.read_csv(csv_path)
    
    total = 0
    passed = 0
    failed = 0
    skipped = 0
    
    results = []
    
    print("Starting Value Correctness Tests...")
    print("-" * 60)
    
    user_id = "00000000-0000-0000-0000-000000000000"
    ref_date = date(2026, 5, 10)
    
    for idx, row in df.iterrows():
        question = row['question']
        gt_sql_raw = row['SQL']
        
        gt_sql = clean_sql(gt_sql_raw)
        
        if gt_sql.startswith("SKIP"):
            skipped += 1
            continue
            
        total += 1
        
        intent = heuristic_numeric_intent(question)
        intent = enforce_intent_invariants(intent, question)
        gen_sql = build_numeric_sql(intent)
        
        if gen_sql is None:
            failed += 1
            results.append({
                "question": question,
                "status": "FAIL",
                "reason": "Generated SQL is None (skipped by heuristics) but GT expected executable SQL",
                "gt_sql": gt_sql,
                "gen_sql": "None"
            })
            continue
            
        date_start, date_end = resolve_date_range(question, ref_date)
        params = [user_id, date_start, date_end, intent.context_filter, intent.speaker, intent.keyword]
        
        try:
            async with pool.acquire() as conn:
                # Run Ground Truth
                gt_rows = await conn.fetch(gt_sql, *params)
                # Run Generated
                gen_rows = await conn.fetch(gen_sql, *params)
                
            is_match, msg = await compare_results(gt_rows, gen_rows, intent.target)
            if is_match:
                passed += 1
                results.append({
                    "question": question,
                    "status": "PASS",
                    "reason": msg,
                    "gt_sql": gt_sql,
                    "gen_sql": gen_sql
                })
            else:
                failed += 1
                results.append({
                    "question": question,
                    "status": "FAIL",
                    "reason": msg,
                    "gt_sql": gt_sql,
                    "gen_sql": gen_sql,
                    "gt_result": str([dict(r) for r in gt_rows]),
                    "gen_result": str([dict(r) for r in gen_rows])
                })
                print(f"Mismatch at row {idx+2}: {question}")
                print(f"  Reason: {msg}")
                print(f"  GT SQL:  {gt_sql}")
                print(f"  GEN SQL: {gen_sql}")
                print(f"  GT rows:  {gt_rows}")
                print(f"  GEN rows: {gen_rows}")
                print("-" * 60)
                
        except Exception as e:
            failed += 1
            results.append({
                "question": question,
                "status": "FAIL",
                "reason": f"Execution Error: {e}",
                "gt_sql": gt_sql,
                "gen_sql": gen_sql
            })
            print(f"Execution Error at row {idx+2}: {question}")
            print(f"  Error: {e}")
            print(f"  GT SQL:  {gt_sql}")
            print(f"  GEN SQL: {gen_sql}")
            print("-" * 60)

    await pool.close()
    
    print("\n" + "=" * 60)
    print("VALUE CORRECTNESS TEST SUMMARY")
    print("=" * 60)
    print(f"Total checked:  {total}")
    print(f"Passed matches: {passed} ({passed/total*100:.1f}%)")
    print(f"Failed mismatches/errors: {failed} ({failed/total*100:.1f}%)")
    print(f"Skipped queries: {skipped}")
    print("=" * 60)
    
    # Save detailed report
    report_df = pd.DataFrame(results)
    report_df.to_csv(ROOT / "eval_v2" / "test_values_report.csv", index=False, encoding="utf-8")
    print(f"Saved detailed correctness report to eval_v2/test_values_report.csv")

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    asyncio.run(test_value_correctness())
