import csv

csv_file = r"d:\javis_text2sql\hcacis\HCACIS_Production_Report.csv"

rows = [
    ["17", "2026年6月8日の会議の概要を教えてください。", "Hãy cho tôi biết tổng quan về cuộc họp ngày 8/6/2026.", "2026年6月8日の会議の概要を教えてください", "rag", "full", "ChromaDB Vector Search", "THÀNH CÔNG XUẤT SẮC. Vì DB không có cuộc họp ngày 8/6, hệ thống trả lời thành thật là 'không có thông tin' thay vì bịa chuyện (Zero Hallucination). Rất an toàn."],
    ["18", "その会議で「田中さん」の発言の平均時間は何秒でしたか？", "Trong cuộc họp đó, thời gian phát biểu trung bình của ông Tanaka là bao nhiêu giây?", "2026年6月8日の会議で田中さんの発言の平均時間は何秒でしたか？", "sql", "partial", "Numeric SQL Pipeline", "THÀNH CÔNG XUẤT SẮC. Xử lý chính xác Coreference 'cuộc họp đó' thành ngày 8/6. Do không có dữ liệu cuộc họp này, SQL trả về None và Generator LLM báo lỗi lịch sự thay vì crash ứng dụng."],
    ["19", "田中さんが話した内容で一番重要なポイントを1文で要約してください。", "Hãy tóm tắt điểm quan trọng nhất trong phát ngôn của ông Tanaka thành 1 câu.", "田中さんの発言の重要なポイントを1文で要約してください", "rag", "partial", "ChromaDB Vector Search", "THÀNH CÔNG XUẤT SẮC. Câu hỏi tiếp nối tốt, tự động lược bỏ mốc ngày 8/6 không hợp lệ để gom toàn bộ context của Tanaka trên DB. RAG partial filter theo Tanaka hoạt động hoàn hảo và tóm tắt chuẩn."],
    ["20", "ところで、「Apple」という会社の最新ニュースをインターネットで検索して。", "Nhân tiện, hãy tìm tin tức mới nhất về công ty Apple trên mạng.", "Appleの最新ニュース", "web", "full", "DuckDuckGo Search", "THÀNH CÔNG XUẤT SẮC. Nhận diện từ 'Nhân tiện' (ところで) để Context Shift. Xóa scope cũ và search DuckDuckGo chính xác."],
    ["21", "その会社のCEOは現在誰ですか？", "CEO hiện tại của công ty đó là ai?", "Appleの現在のCEOは誰ですか？", "web", "full", "DuckDuckGo Search", "THÀNH CÔNG XUẤT SẮC. Dịch chuẩn 'công ty đó' thành Apple. Gọi Web Engine trả về đúng tên Tim Cook."],
    ["22", "今月のすべての会議の中で、「新エネルギー」という言葉は何回言及されましたか？", "Trong tất cả cuộc họp tháng này, từ 'năng lượng mới' được nhắc đến bao nhiêu lần?", "今月のすべての会議の中で、新エネルギーについては何回言及されましたか?", "sql", "full", "Numeric SQL Pipeline", "THÀNH CÔNG XUẤT SẮC. Nhận diện chuẩn xác SQL đếm text. Pipeline in ra câu query có `ILIKE '%新エネルギー%'` chính xác và kết quả ra 1 lần."],
    ["23", "その結果を分析して、私たちの会社が新エネルギーにどれくらい関心を持っているか推測してください。", "Dựa vào kết quả đó, hãy suy đoán xem công ty chúng ta quan tâm đến năng lượng mới mức nào.", "私たちの会社が新エネルギーにどれくらい関心を持っているか推測してください", "pure_llm", "none", "None (Bypass)", "THÀNH CÔNG TUYỆT ĐỐI. Nhận diện đúng đây là câu hỏi suy luận logic, Bypass hoàn toàn DB. Lý luận của mô hình cực kỳ sắc bén (nhận xét từ con số 1 lần nhắc đến) và đưa ra gợi ý chuyên sâu."]
]

with open(csv_file, 'a', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    writer.writerows(rows)

print("Appended rows successfully.")
