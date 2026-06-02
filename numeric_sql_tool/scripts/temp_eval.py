import sys
from pathlib import Path
import pandas as pd
from datetime import date

ROOT = Path(".").resolve()
sys.path.insert(0, str(ROOT / "src"))

from numeric_sql_tool.heuristics import heuristic_numeric_intent
from numeric_sql_tool.pipeline import build_numeric_sql

csv_path = ROOT / "db" / "numeric_sql_testcases_ja.csv"
df = pd.read_csv(csv_path)

results = []
ref_date = date(2026, 5, 28)

for idx, row in df.iterrows():
    row_num = idx + 2
    q = str(row['question']).strip()
    csv_sql = str(row['sql']).strip() # Generating CSV used lowercase 'sql'
    
    # Run the heuristic parser
    intent = heuristic_numeric_intent(q)
    expected_sql = build_numeric_sql(intent)
    
    # Determine actual correct behavior based on rules
    q_lower = q.lower()
    should_be_skip = False
    skip_reason = ""
    
    # Logic copied from original eval_cases.py
    if any(k in q_lower for k in ["何について", "議題", "要約", "合意された内容", "発言したのは誰", "詳しく説明", "ローンチについて話した", "ローンチについて話す"]):
        should_be_skip = True
        skip_reason = "Qualitative/semantic"
    elif "いくらでしたか" in q_lower or "予算はいくら" in q_lower:
        should_be_skip = True
        skip_reason = "Detailed figure"
    elif any(k in q_lower for k in ["何分頃", "何秒頃", "何時頃", "何秒目", "いつ発言"]):
        should_be_skip = True
        skip_reason = "Detailed timestamp"
    elif "いつですか" in q_lower and not any(k in q_lower for k in ["最も", "一番"]):
        should_be_skip = True
        skip_reason = "Time based on topic"
            
    is_skip = should_be_skip or intent.operator in {"skip", "none"} or intent.target in {"none", "time_start_sec"}
    
    if is_skip:
        actual_expected = "SKIP (operator=skip, target=none)"
    else:
        actual_expected = expected_sql
        
    def normalize(s):
        if not s or pd.isna(s):
            return ""
        s = str(s).replace("\n", " ").replace("\r", "")
        s = " ".join(s.split())
        return s.lower()
        
    norm_csv = normalize(csv_sql)
    norm_expected = normalize(actual_expected)
    
    is_wrong = False
    reason = ""
    
    if is_skip:
        if "skip" not in csv_sql.lower():
            is_wrong = True
            reason = f"Phải là SKIP. Lý do: {skip_reason}."
    else:
        if "skip" in csv_sql.lower():
            is_wrong = True
            reason = "Phải sinh SQL (đây là câu hỏi định lượng/đếm số cuộc họp)."
        elif norm_csv != norm_expected:
            is_wrong = True
            if "group by" in csv_sql.lower() and "group_by" not in str(actual_expected).lower() and "group by" not in str(actual_expected).lower():
                reason = "SQL không khớp. CSV sử dụng GROUP BY dư thừa cho câu hỏi truy vấn 1 ngày duy nhất."
            else:
                reason = "SQL không khớp về cấu trúc truy vấn hoặc điều kiện lọc."

    results.append({
        "row": row_num,
        "question": q,
        "csv_sql": csv_sql,
        "expected_sql": actual_expected,
        "is_wrong": is_wrong,
        "reason": reason
    })

report_path = ROOT / "eval" / "evaluation_report_ja_new.md"

with open(report_path, "w", encoding="utf-8") as f:
    f.write("# Báo cáo Đánh giá Test Case Tiếng Nhật Mới\n\n")
    f.write("| Dòng | Câu hỏi | SQL thực tế | Cú pháp mong muốn | Kết quả |\n")
    f.write("|---|---|---|---|---|\n")
    
    incorrect_count = 0
    correct_count = 0
    
    for r in results:
        question_escaped = r["question"].replace("\n", " <br> ")
        csv_sql_escaped = str(r["csv_sql"]).replace("\n", " <br> ").replace("|", "\\|")
        expected_sql_escaped = str(r["expected_sql"]).replace("\n", " <br> ").replace("|", "\\|")
        
        if r["is_wrong"]:
            incorrect_count += 1
            status = f"🔴 **Sai**<br>{r['reason']}"
        else:
            correct_count += 1
            status = "🟢 **Đúng**"
            
        f.write(f"| {r['row']} | {question_escaped} | `{csv_sql_escaped}` | `{expected_sql_escaped}` | {status} |\n")

print(f"Báo cáo mới đã được tạo tại: {report_path}")
print(f"Tổng số case Đúng: {correct_count}, Sai: {incorrect_count}")
