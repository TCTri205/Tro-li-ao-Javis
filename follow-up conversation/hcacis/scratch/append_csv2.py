import csv

csv_file = r"d:\javis_text2sql\hcacis\HCACIS_Production_Report.csv"

rows = [
    ["17", "2026年5月の会議の中で、会議の件数は合計でいくつありましたか？", "Trong tháng 5 năm 2026 có tổng cộng bao nhiêu cuộc họp?", "2026年5月の会議の中で、会議の件数は合計でいくつありましたか？", "sql", "full", "Numeric SQL Pipeline", "THÀNH CÔNG XUẤT SẮC. Lỗi 'is_semantic' đã được fix hoàn toàn. Câu hỏi có tính chất định lượng (đếm) đã đi thẳng vào Pipeline SQL và chạy lệnh COUNT() chính xác ra 5 cuộc họp."],
    ["18", "2026年5月の会議の中で、「セキュリティ」について言及された会議の合計時間は何秒ですか？", "Tổng thời gian các cuộc họp tháng 5 nhắc đến 'bảo mật' là bao nhiêu giây?", "2026年5月の会議の中で、「セキュリティ」について言及された会議の合計時間は何秒ですか？", "sql", "partial", "Numeric SQL Pipeline", "THÀNH CÔNG XUẤT SẮC. Luật Invariant đã hoạt động hoàn hảo. Từ khóa 'security' được ép chuyển sang `context_filter` thay vì `entity_filter`. Pipeline SUM trả về 3610s chính xác."],
    ["19", "それらの会議では、セキュリティのどんな問題について話し合われましたか？", "Trong các cuộc họp đó, những vấn đề bảo mật nào đã được thảo luận?", "2026年5月の会議の中でセキュリティについて言及された会議では、セキュリティのどんな問題について話し合われましたか？", "rag", "partial", "ChromaDB Vector Search", "THÀNH CÔNG TUYỆT ĐỐI. Lỗi ảo giác History Bias (sinh nhảm block SQL) đã được dập tắt. Generator chỉ gọi đúng dữ liệu RAG ra để trả lời nội dung thảo luận."],
    ["20", "2026年5月のすべての会議の中で、一番短い会議の時間は何秒でしたか？", "Trong tất cả các cuộc họp tháng 5, cuộc họp ngắn nhất kéo dài bao nhiêu giây?", "2026年5月のすべての会議の中で、一番短い会議の時間は何秒でしたか？", "sql", "full", "Numeric SQL Pipeline", "THÀNH CÔNG XUẤT SẮC. Hệ thống Semantic Cache đã hoạt động chuẩn sau khi nâng threshold lên 0.95. Câu MIN không còn bị nhầm lẫn với cache câu SUM. Pipeline SQL trả đúng 25s."],
    ["21", "その一番短い会議で、どのような挨拶が交わされましたか？", "Trong cuộc họp ngắn nhất đó, mọi người đã chào hỏi nhau thế nào?", "2026年5月の最も短い会議でどのような挨拶が交わされましたか？", "rag", "partial", "ChromaDB Vector Search", "THÀNH CÔNG XUẤT SẮC. System detect được Follow-up liên kết với cuộc họp 25s và chạy RAG chính xác để lục lại lời chào."],
    ["22", "2026年5月の一つの会議あたりの平均時間は何秒ですか？", "Thời gian trung bình một cuộc họp trong tháng 5 là bao nhiêu giây?", "2026年5月の一つの会議あたりの平均時間は何秒ですか？", "sql", "full", "Numeric SQL Pipeline", "THÀNH CÔNG XUẤT SẮC. Intent AVG được bắt dính và Pipeline xử lý chuẩn xác 1645.2s."],
    ["23", "会議の中で、誰かが新しいソフトウェアの購入を提案した会議はありますか？", "Có cuộc họp nào có người đề xuất mua phần mềm mới không?", "会議の中で、新しいソフトウェアの購入を提案した会議はありますか？", "rag", "full", "ChromaDB Vector Search", "THÀNH CÔNG XUẤT SẮC. Nhận diện cực chuẩn câu hỏi tìm kiếm nội dung (Semantic) và đẩy qua RAG mà không bị kẹt ở SQL Pipeline."],
    ["24", "話題は変わりますが、DuckDuckGoで最新のAIトレンドについて検索して、簡単に教えてください。", "Đổi chủ đề nhé, hãy tìm xu hướng AI mới nhất trên DuckDuckGo và nói ngắn gọn cho tôi.", "最新のAIトレンドについて教えて", "web", "full", "DuckDuckGo Search", "THÀNH CÔNG XUẤT SẮC. Chuyển đổi ngữ cảnh hoàn hảo với cụm 'Đổi chủ đề'. System wipe graph context và sử dụng DuckDuckGo Tool chuẩn xác."],
    ["25", "もし新しいAIソフトウェアが1500ドルだとしたら、現在の為替レートで日本円でいくらになりますか？", "Nếu phần mềm AI đó giá 1500 USD, thì tính theo tỷ giá hiện tại là bao nhiêu Yên Nhật?", "1500ドルは現在の為替レートで日本円でいくらになりますか?", "web", "full", "DuckDuckGo Search", "THÀNH CÔNG XUẤT SẮC. Tiếp tục sử dụng Web Engine để tra tỷ giá tiền tệ realtime thay vì tìm trong Database nội bộ."]
]

with open(csv_file, 'a', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    writer.writerows(rows)

print("Appended new evaluated rows successfully.")
