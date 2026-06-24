import csv

csv_file = r"d:\javis_text2sql\hcacis\HCACIS_Production_Report.csv"

new_rows = [
    ["30", "2026年5月26日の会議では、主に何が話し合われましたか？", "Trong cuộc họp ngày 26/5/2026, chủ yếu đã thảo luận những gì?", "2026年5月26日の会議では、主に何が話し合われましたか？", "rag", "full", "ChromaDB Vector Search", "THÀNH CÔNG TỐT. RAG engine nhận diện và trích xuất đúng nội dung cuộc họp ngày 26/5. Không bị ảo giác sinh SQL."],
    ["31", "その会議の中で、「佐藤さん」は何回発言しましたか？", "Trong cuộc họp đó, ông Sato đã phát biểu bao nhiêu lần?", "2026年5月26日の会議の中で、佐藤さんは何回発言しましたか？", "sql", "partial", "Numeric SQL Pipeline", "THÀNH CÔNG XUẤT SẮC. Lớp Memory xử lý Coreference chính xác (cuộc họp đó -> 26/5). LLM tạo SQL chính xác (COUNT WHERE speaker='佐藤')."],
    ["32", "佐藤さんは予算やコストについてどのような意見を持っていましたか？", "Ông Sato có ý kiến gì về ngân sách và chi phí?", "佐藤さんは予算やコストについてどのような意見を持っていましたか？", "rag", "partial", "ChromaDB Vector Search", "THÀNH CÔNG XUẤT SẮC. Lớp Planner tái sử dụng ngữ cảnh (Context) xuất sắc, truyền ID vào ChromaDB. Đã khắc phục hoàn toàn lỗi Format Hallucination (Zero Hallucination SQL)."],
    ["33", "その会議で、佐藤さんの発言の中で一番長かったものは何秒でしたか？", "Trong cuộc họp đó, phát biểu dài nhất của ông Sato là bao nhiêu giây?", "佐藤さんの発言の中で一番長かったものは何秒でしたか？", "sql", "partial", "Numeric SQL Pipeline", "THÀNH CÔNG XUẤT SẮC. Lọc chính xác giá trị MAX cho duration. SQL từ LLM sinh ra logic rất chuẩn (MAX duration)."],
    ["34", "話題を変えますが、「Microsoft」の最新動向をインターネットで検索して。", "Chuyển chủ đề, hãy tìm kiếm xu hướng mới nhất của Microsoft trên mạng.", "Microsoftの最新動向", "web", "full", "DuckDuckGo Search", "THÀNH CÔNG XUẤT SẮC. Nhận diện lệnh đổi chủ đề, xoá bộ nhớ cũ và gọi Web Engine mượt mà. Không bị ảo giác mã code SQL."],
    ["35", "その内容を英語で1文に要約してください。", "Hãy tóm tắt nội dung đó bằng tiếng Anh trong 1 câu.", "現在の会話内容を英語で1文に要約してください。", "pure_llm", "none", "None (Bypass)", "THÀNH CÔNG XUẤT SẮC. Hoàn toàn Bypass Database, nhảy trực tiếp qua bộ nhớ đệm (Cache) của Web Engine để tóm tắt và dịch thuật."],
    ["36", "2026年5月のすべての会議のうち、参加者（スピーカー数）が5人以上だった会議はいくつありますか？", "Trong tất cả các cuộc họp tháng 5 năm 2026, có bao nhiêu cuộc họp có từ 5 người tham gia (speaker) trở lên?", "2026年5月の会議で参加者が5人以上だった会議は何件ありますか？", "sql", "full", "Numeric SQL Pipeline", "THÀNH CÔNG 80%. Định tuyến SQL thành công. Điểm trừ: Pipeline cũ không bắt được điều kiện '>= 5' (chỉ sinh query theo thời gian). Tuy nhiên LLM Generated SQL sinh mã rất xuất sắc, bù đắp được khuyết điểm pipeline hiện tại."]
]

with open(csv_file, 'a', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    writer.writerows(new_rows)

print("Appended 7 rows for Scenario 4.")
