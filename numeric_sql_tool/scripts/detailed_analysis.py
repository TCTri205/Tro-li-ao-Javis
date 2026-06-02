import sys
import asyncio
from pathlib import Path
import pandas as pd
from datetime import date

sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from numeric_sql_tool.config import Settings
from numeric_sql_tool.db_utils import create_pool
from numeric_sql_tool.pipeline import run_numeric_pipeline

DEFAULT_REFERENCE_DATE = date(2026, 5, 28)
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000000"

async def analyze():
    csv_path = Path("eval/combined_200_testcases_ja.csv")
    df = pd.read_csv(csv_path)
    
    settings = Settings.from_env()
    pool = await create_pool(settings.database_url)
    
    print(f"Loaded {len(df)} test cases.")
    
    samples_by_category = {}
    
    for idx, row in df.iterrows():
        q = row['question']
        gt_sql = row['sql']
        
        res = await run_numeric_pipeline(
            q, pool, None, DEFAULT_USER_ID, DEFAULT_REFERENCE_DATE
        )
        
        sql = res.metadata.get("sql")
        skipped = res.metadata.get("skipped", False)
        
        # Categorize
        category = "OTHER"
        if skipped:
            category = "SKIP"
        elif "COUNT(DISTINCT" in str(sql) and "GROUP BY" not in str(sql):
            category = "COUNT_TOTAL"
        elif "COUNT(DISTINCT" in str(sql) and "GROUP BY" in str(sql):
            category = "COUNT_GROUP"
        elif "SUM(" in str(sql) and "GROUP BY" not in str(sql):
            category = "SUM_TOTAL"
        elif "SUM(" in str(sql) and "GROUP BY" in str(sql):
            category = "SUM_GROUP"
        elif "AVG(" in str(sql):
            category = "AVG"
        elif "ORDER BY" in str(sql):
            category = "EXTREME_DURATION"
            
        if category not in samples_by_category:
            samples_by_category[category] = []
            
        samples_by_category[category].append({
            "idx": idx + 2,
            "q": q,
            "sql": sql,
            "rows": res.rows,
            "gt_sql": gt_sql
        })
        
    print("\n=== SUMMARY OF CATEGORIES ===")
    for cat, items in samples_by_category.items():
        print(f"Category {cat}: {len(items)} cases")
        # Print top 2 examples
        for item in items[:2]:
            print(f"  [{item['idx']}] Q: {item['q']}")
            print(f"    SQL: {item['sql']}")
            print(f"    Result: {item['rows']}")
            
    # Let's inspect some potential edge cases
    print("\n=== EDGE CASES INSPECTION ===")
    
    # 1. Ask about duration but got count?
    print("Checking if any duration query got count:")
    for cat in ["SUM_TOTAL", "AVG", "EXTREME_DURATION"]:
        if cat in samples_by_category:
            for item in samples_by_category[cat]:
                if any(w in item['q'] for w in ["件数", "回数", "何回"]):
                    print(f"  Potential issue: Q '{item['q']}' categorized as {cat}")
                    
    # 2. Ask about count but got duration?
    print("Checking if any count query got duration:")
    for cat in ["COUNT_TOTAL", "COUNT_GROUP"]:
        if cat in samples_by_category:
            for item in samples_by_category[cat]:
                if any(w in item['q'] for w in ["時間", "長さ", "何秒"]):
                    print(f"  Potential issue: Q '{item['q']}' categorized as {cat}")
                    
    # 3. Speaker questions check
    print("Checking Speaker grouping cases:")
    for cat in ["COUNT_GROUP", "SUM_GROUP"]:
        if cat in samples_by_category:
            for item in samples_by_category[cat]:
                if "話者" in item['q'] or "人" in item['q']:
                    print(f"  Q: '{item['q']}' -> SQL: {item['sql']}")
                    
    await pool.close()

if __name__ == "__main__":
    asyncio.run(analyze())
