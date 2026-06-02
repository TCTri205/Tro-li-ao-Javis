import sys
from pathlib import Path
import pandas as pd
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from numeric_sql_tool.heuristics import heuristic_numeric_intent
from numeric_sql_tool.pipeline import build_numeric_sql

csv_path = ROOT / "eval" / "numeric_sql_testcases_ja.csv"
df = pd.read_csv(csv_path)

results = []
ref_date = date(2026, 5, 28)

for idx, row in df.iterrows():
    row_num = idx + 2  # Excel row number (1-based, header is 1)
    q = str(row['question']).strip()
    csv_sql = str(row['SQL']).strip()
    csv_eval = str(row.get('Đánh giá', '')).strip()
    
    # Run the heuristic parser
    intent = heuristic_numeric_intent(q)
    expected_sql = build_numeric_sql(intent)
    
    # Determine actual correct behavior based on rules
    q_lower = q.lower()
    should_be_skip = False
    skip_reason = ""
    
    # 1. Qualitative/semantic questions
    if "何について" in q_lower or "議題" in q_lower or "要約" in q_lower or "合意された内容" in q_lower or "発言したのは誰" in q_lower or "詳しく説明" in q_lower or "ローンチについて話した" in q_lower or "ローンチについて話す" in q_lower:
        should_be_skip = True
        skip_reason = "Câu hỏi định tính/ngữ nghĩa (hỏi về chủ đề thảo luận, tóm tắt hoặc người phát biểu)"
    elif "いくらでしたか" in q_lower or "予算はいくら" in q_lower:
        should_be_skip = True
        skip_reason = "Hỏi về số liệu chi tiết trong nội dung họp (như số tiền ngân sách), không có trong metadata"
    elif "何分頃" in q_lower or "何秒頃" in q_lower or "何時頃" in q_lower or "何秒目" in q_lower or "いつ発言" in q_lower:
        should_be_skip = True
        skip_reason = "Hỏi mốc thời gian chi tiết trong cuộc họp (turn-level timestamps)"
    elif "いつですか" in q_lower or "いつですか？" in q_lower:
        # Nếu hỏi "khi nào" dựa trên chủ đề (không phải tìm cuộc họp dài nhất/ngắn nhất) thì phải SKIP
        if "最も" not in q_lower and "一番" not in q_lower:
            should_be_skip = True
            skip_reason = "Hỏi thời gian họp dựa trên chủ đề thảo luận (cần tìm kiếm ngữ nghĩa)"
            
    is_skip = should_be_skip or intent.operator in {"skip", "none"} or intent.target in {"none", "time_start_sec"}
    
    if is_skip:
        actual_expected = "SKIP (operator=skip, target=none)"
    else:
        actual_expected = expected_sql
        
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
            return " ".join(val.lower().split())
        if clean(sql_a) == clean(sql_b):
            return True
        return sql_structure_key(sql_a) == sql_structure_key(sql_b)
        
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
        elif not sql_semantically_equal(csv_sql, actual_expected):
            is_wrong = True
            # Kiểm tra xem có phải lỗi gom nhóm dư thừa không
            if "group by" in csv_sql.lower() and "group by" not in actual_expected.lower():
                reason = "SQL không khớp. CSV sử dụng GROUP BY dư thừa cho câu hỏi truy vấn 1 ngày duy nhất."
            else:
                reason = "SQL không khớp về cấu trúc truy vấn hoặc điều kiện lọc."


    results.append({
        "row": row_num,
        "question": q,
        "csv_sql": csv_sql,
        "csv_eval": csv_eval,
        "expected_sql": actual_expected,
        "is_wrong": is_wrong,
        "reason": reason
    })

report_path = ROOT / "eval" / "evaluation_report.md"

with open(report_path, "w", encoding="utf-8") as f:
    f.write("# Báo cáo Đánh giá chi tiết các Test Case Tiếng Nhật (Numeric SQL)\n\n")
    f.write("Dưới đây là bảng đối chiếu chi tiết giữa câu lệnh SQL định nghĩa sẵn trong file CSV và hành vi chuẩn mong muốn của hệ thống.\n\n")
    f.write("| Dòng | Câu hỏi | SQL trong CSV | Cú pháp đúng (Expected) | Đánh giá gốc | Kết quả đối chiếu (Model Assessment) |\n")
    f.write("|---|---|---|---|---|---|\n")
    
    incorrect_count = 0
    correct_count = 0
    
    for r in results:
        question_escaped = r["question"].replace("\n", " <br> ")
        csv_sql_escaped = r["csv_sql"].replace("\n", " <br> ").replace("|", "\\|")
        expected_sql_escaped = r["expected_sql"].replace("\n", " <br> ").replace("|", "\\|")
        
        if r["is_wrong"]:
            incorrect_count += 1
            model_assessment = f"🔴 **Sai**<br>Lý do: {r['reason']}<br>Nên là: `{expected_sql_escaped}`"
        else:
            correct_count += 1
            model_assessment = "🟢 **Đúng**"
            
        f.write(f"| {r['row']} | {question_escaped} | `{csv_sql_escaped}` | `{expected_sql_escaped}` | {r['csv_eval']} | {model_assessment} |\n")

try:
    print(f"Báo cáo đã được tạo tại: {report_path}")
    print(f"Tổng số case Đúng: {correct_count}, Sai: {incorrect_count}")
except UnicodeEncodeError:
    print(f"Report written to: {report_path}")
    print(f"Total Correct: {correct_count}, Wrong: {incorrect_count}")

