import csv

csv_file = r"d:\javis_text2sql\hcacis\HCACIS_Production_Report.csv"

with open(csv_file, 'r', encoding='utf-8-sig') as f:
    reader = csv.reader(f)
    rows = list(reader)

for i, row in enumerate(rows):
    if len(row) > 0 and row[0] == "26":
        rows[i][-1] = "THÀNH CÔNG (Layer 1-3) Nhưng LỖI FORMAT (Layer 4). Hệ thống Router/Planner hoạt động hoàn hảo: Lấy đúng khóa ngoại để filter ChromaDB, trả về đúng dữ liệu RAG (Chứng minh qua việc không có block Pipeline Generated SQL). Tuy nhiên, Generator LLM bị dính History Bias (bắt chước format từ câu trả lời trước đó) nên tự ảo giác sinh ra thêm một khối LLM Generated SQL vô nghĩa. Cần sửa Prompt Layer 4 để cấm sinh SQL khi intent khác sql."

with open(csv_file, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    writer.writerows(rows)

print("Fixed row 26")
