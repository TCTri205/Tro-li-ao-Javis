import csv

csv_file = r"d:\javis_text2sql\hcacis\HCACIS_Production_Report.csv"

rows = [
    ["24", "2026年5月のすべての会議の合計時間は何秒ですか？", "Tổng thời gian của tất cả các cuộc họp trong tháng 5 năm 2026 là bao nhiêu giây?", "2026年5月のすべての会議の合計時間は何秒ですか？", "sql", "full", "Numeric SQL Pipeline", "THÀNH CÔNG XUẤT SẮC. Nhận diện chính xác ý định SQL và query chính xác khoảng thời gian tháng 5 để tính tổng SUM(duration_seconds)."],
    ["25", "その中で一番短かった会議のIDは何ですか？", "Trong số đó, ID của cuộc họp ngắn nhất là gì?", "2026年5月の会議の中で一番短かった会議のIDは何ですか？", "sql", "partial", "Numeric SQL Pipeline", "THÀNH CÔNG XUẤT SẮC. Giải quyết rất mượt Coreference 'trong số đó' thành 'trong các cuộc họp tháng 5 năm 2026'. SQL sinh ra chính xác lệnh lấy MIN/ORDER BY ASC."],
    ["26", "その一番短かった会議では、どんな結論が出ましたか？", "Trong cuộc họp ngắn nhất đó, đã có kết luận gì?", "一番短かった会議では、どんな結論が出ましたか？", "rag", "partial", "ChromaDB Vector Search", "THÀNH CÔNG XUẤT SẮC. Lấy đúng khóa ngoại (transcript_id) từ câu SQL trước đó để filter Vector DB. Nhận diện chuẩn xác file dữ liệu đó không có ghi chú kết luận nào nên trả lời chân thật (Zero Hallucination)."],
    ["27", "今の説明を英語に翻訳してください。", "Hãy dịch lời giải thích vừa rồi sang tiếng Anh.", "現在の説明を英語に翻訳してください", "pure_llm", "none", "None (Bypass)", "THÀNH CÔNG XUẤT SẮC. Nhận diện rõ đây là yêu cầu thao tác ngôn ngữ, hoàn toàn bypass database và dùng LLM chuyển ngữ hoàn hảo nội dung lịch sử chat."],
    ["28", "話題を変えますが、「Google」の最新のAI技術についてネットで調べて。", "Chuyển chủ đề, hãy tìm trên mạng về công nghệ AI mới nhất của Google.", "Googleの最新のAI技術についてネットで調べて", "web", "full", "DuckDuckGo Search", "THÀNH CÔNG XUẤT SẮC. Lệnh 'Chuyển chủ đề' được xử lý dứt điểm, làm sạch context cũ và đổi hướng sang gọi Web Engine chính xác cho Google."],
    ["29", "その技術の主な特徴を3つ挙げてください。", "Hãy nêu 3 đặc điểm chính của công nghệ đó.", "Google AI技術の主な特徴を3つ挙げてください", "pure_llm", "none", "None (Bypass)", "THÀNH CÔNG XUẤT SẮC. Nhận diện đúng Coreference 'công nghệ đó' thành 'Google AI', đồng thời nhận diện được dữ liệu đã nằm sẵn trong bộ nhớ từ lượt Search Web trước nên chuyển sang dùng Pure LLM để tóm tắt 3 đặc điểm."]
]

with open(csv_file, 'a', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    writer.writerows(rows)

print("Appended scenario 3 rows successfully.")
