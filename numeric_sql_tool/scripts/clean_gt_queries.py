import sys
from pathlib import Path
import pandas as pd

# Add src to sys.path
sys.path.insert(0, str(Path("d:/VJ/Tro-li-ao-Javis/numeric_sql_tool/src")))

from numeric_sql_tool.heuristics import heuristic_numeric_intent
from numeric_sql_tool.pipeline import build_numeric_sql

def clean_all():
    csv_path = Path("d:/VJ/Tro-li-ao-Javis/numeric_sql_tool/eval_v2/questions_GTqueries.csv")
    df = pd.read_csv(csv_path)
    
    updated_count = 0
    
    for idx, row in df.iterrows():
        question = row['question']
        gt_sql = row['SQL']
        
        intent = heuristic_numeric_intent(question)
        generated_sql = build_numeric_sql(intent)
        
        if generated_sql is None:
            expected_sql = "SKIP (operator=skip, target=none)"
        else:
            expected_sql = generated_sql
            
        # Standardize spaces for comparison
        gt_standardized = " ".join(str(gt_sql).strip().split())
        expected_standardized = " ".join(expected_sql.strip().split())
        
        # Strip outer quotes if any
        if gt_standardized.startswith('"') and gt_standardized.endswith('"'):
            gt_standardized = gt_standardized[1:-1].strip()
            gt_standardized = " ".join(gt_standardized.split())
            
        if gt_standardized != expected_standardized:
            updated_count += 1
            df.at[idx, 'SQL'] = expected_sql
            
    # Save the updated DataFrame back to the CSV
    df.to_csv(csv_path, index=False, encoding='utf-8')
    print(f"Successfully updated {updated_count} queries in {csv_path}.")

if __name__ == "__main__":
    clean_all()
