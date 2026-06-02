import sys
import pandas as pd
from pathlib import Path

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    csv_path = Path("eval/combined_200_testcases_ja.csv")
    if not csv_path.exists():
        print(f"Error: {csv_path} does not exist.")
        return
        
    df = pd.read_csv(csv_path)
    
    # 1. Update '先月の平均的な会議の長さは？'
    # Change COUNT to AVG(t.duration_seconds)
    avg_sql = (
        "SELECT COALESCE(AVG(t.duration_seconds), 0) AS value FROM transcripts t "
        "WHERE ($1::uuid IS NULL OR t.user_id = $1::uuid) "
        "AND ($2::date IS NULL OR t.meeting_date >= $2::date) "
        "AND ($3::date IS NULL OR t.meeting_date <= $3::date) "
        "AND ($4::text IS NULL OR t.summary ILIKE '%' || $4 || '%' OR t.raw_text ILIKE '%' || $4 || '%')"
    )
    mask1 = df['question'] == '先月の平均的な会議 of length'
    # Wait, the exact question is '先月の平均的な会議の長さは？'
    mask1 = df['question'] == '先月の平均的な会議の長さは？'
    if mask1.any():
        df.loc[mask1, 'sql'] = avg_sql
        print("Updated '先月の平均的な会議の長さは？' to AVG duration SQL.")
    else:
        print("Warning: '先月の平均的な会議の長さは？' not found.")
        
    # 2. Update '先週の会議件数と合計時間は？'
    # Change to SKIP
    mask2 = df['question'] == '先週の会議件数と合計時間は？'
    if mask2.any():
        df.loc[mask2, 'sql'] = 'SKIP (operator=skip, target=none)'
        print("Updated '先週の会議件数と合計時間は？' to SKIP.")
    else:
        print("Warning: '先週の会議件数と合計時間は？' not found.")
        
    # 3. Update '今月の会議は何件ですか？それとも先月？'
    # Change to SKIP
    mask3 = df['question'] == '今月の会議は何件ですか？それとも先月？'
    if mask3.any():
        df.loc[mask3, 'sql'] = 'SKIP (operator=skip, target=none)'
        print("Updated '今月の会議は何件ですか？それとも先月？' to SKIP.")
    else:
        print("Warning: '今月の会議は何件ですか？それとも先月？' not found.")
        
    df.to_csv(csv_path, index=False, encoding='utf-8')
    print(f"Saved changes to {csv_path}")

if __name__ == "__main__":
    main()
