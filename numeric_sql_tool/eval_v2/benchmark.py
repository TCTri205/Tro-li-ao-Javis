import sys
import os
import time
import asyncio
import asyncpg
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import date

# Add src to sys.path
ROOT = Path("d:/VJ/Tro-li-ao-Javis/numeric_sql_tool")
sys.path.insert(0, str(ROOT / "src"))

from numeric_sql_tool.heuristics import heuristic_numeric_intent, resolve_date_range, enforce_intent_invariants
from numeric_sql_tool.pipeline import build_numeric_sql

def clean_sql(sql):
    if not sql or pd.isna(sql):
        return ""
    sql = str(sql).strip()
    if sql.startswith('"') and sql.endswith('"'):
        sql = sql[1:-1].strip()
    return sql

async def run_benchmark():
    db_url = "postgresql://app_user:app_password@localhost:54331/app_db"
    pool = await asyncpg.create_pool(db_url)
    
    csv_path = ROOT / "eval_v2" / "questions_GTqueries.csv"
    df = pd.read_csv(csv_path)
    
    print("Preparing benchmark queries...")
    
    user_id = "00000000-0000-0000-0000-000000000000"
    ref_date = date(2026, 5, 10)
    
    executable_queries = []
    
    for idx, row in df.iterrows():
        question = row['question']
        gt_sql = clean_sql(row['SQL'])
        
        if gt_sql.startswith("SKIP"):
            continue
            
        intent = heuristic_numeric_intent(question)
        intent = enforce_intent_invariants(intent, question)
        gen_sql = build_numeric_sql(intent)
        
        if gen_sql is None:
            continue
            
        date_start, date_end = resolve_date_range(question, ref_date)
        params = [user_id, date_start, date_end, intent.context_filter, intent.speaker, intent.keyword]
        
        executable_queries.append({
            "question": question,
            "sql": gen_sql,
            "params": params
        })
        
    print(f"Loaded {len(executable_queries)} queries for benchmarking.")
    print("Running warm-up queries...")
    
    # Warm up connections and Postgres cache
    async with pool.acquire() as conn:
        for eq in executable_queries[:5]:
            await conn.fetch(eq["sql"], *eq["params"])
            
    print("Starting latency measurements (10 iterations per query)...")
    print("-" * 75)
    
    all_latencies = []
    query_stats = []
    
    async with pool.acquire() as conn:
        for idx, eq in enumerate(executable_queries):
            latencies = []
            for _ in range(10):
                start = time.perf_counter()
                await conn.fetch(eq["sql"], *eq["params"])
                end = time.perf_counter()
                latencies.append((end - start) * 1000.0) # in ms
            
            all_latencies.extend(latencies)
            
            lat_arr = np.array(latencies)
            p50 = np.percentile(lat_arr, 50)
            p95 = np.percentile(lat_arr, 95)
            p99 = np.percentile(lat_arr, 99)
            avg = np.mean(lat_arr)
            
            query_stats.append({
                "question": eq["question"],
                "avg_ms": avg,
                "p50_ms": p50,
                "p95_ms": p95,
                "p99_ms": p99
            })
            
    await pool.close()
    
    all_arr = np.array(all_latencies)
    overall_avg = np.mean(all_arr)
    overall_p50 = np.percentile(all_arr, 50)
    overall_p95 = np.percentile(all_arr, 95)
    overall_p99 = np.percentile(all_arr, 99)
    
    print("\n" + "=" * 75)
    print("OVERALL LATENCY BENCHMARK RESULTS")
    print("=" * 75)
    print(f"Total Queries Executed:  {len(executable_queries)}")
    print(f"Total Individual Runs:   {len(all_latencies)}")
    print(f"Average Latency:         {overall_avg:.2f} ms")
    print(f"p50 (Median) Latency:    {overall_p50:.2f} ms")
    print(f"p95 Latency:             {overall_p95:.2f} ms")
    print(f"p99 Latency:             {overall_p99:.2f} ms")
    print("=" * 75)
    
    print("\nQuery-by-Query Statistics:")
    print(f"{'Q#':<3} | {'Avg (ms)':<9} | {'p50 (ms)':<9} | {'p95 (ms)':<9} | {'p99 (ms)':<9} | Question")
    print("-" * 100)
    for i, stat in enumerate(query_stats):
        short_q = stat['question'][:50] + "..." if len(stat['question']) > 50 else stat['question']
        print(f"{i+1:<3} | {stat['avg_ms']:<8.2f} | {stat['p50_ms']:<8.2f} | {stat['p95_ms']:<8.2f} | {stat['p99_ms']:<8.2f} | {short_q}")
    print("-" * 100)
    
    # Save detailed stats
    stats_df = pd.DataFrame(query_stats)
    stats_df.to_csv(ROOT / "eval_v2" / "benchmark_latencies.csv", index=False, encoding="utf-8")
    print(f"\nSaved detailed latency stats to eval_v2/benchmark_latencies.csv")

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    asyncio.run(run_benchmark())
