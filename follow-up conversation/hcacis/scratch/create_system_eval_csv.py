import csv

csv_path = r'd:\javis_text2sql\hcacis\HCACIS_System_Architecture_Evaluation.csv'

headers = [
    "Turn", 
    "Câu hỏi gốc (Nhật)", 
    "Câu hỏi dịch (Việt)", 
    "Câu hỏi đã Rewrite (Follow-up Resolved)", 
    "Engine / Intent", 
    "Retrieval Level", 
    "Công cụ thực thi (Tool)", 
    "Đánh giá hệ thống / Bug Fixes"
]

data = [
    [
        "1",
        "2026年5月の会議の中で、会議の件数は合計でいくつありましたか？",
        "Trong các cuộc họp tháng 5 năm 2026, có tổng cộng bao nhiêu cuộc họp?",
        "2026年5月の会議の中で、会議の件数は合計でいくつありましたか？",
        "sql",
        "full",
        "Numeric SQL Pipeline & Ollama Qwen",
        "THÀNH CÔNG XUẤT SẮC. Layer 1 (Detector) nhận diện độc lập hoàn hảo. Layer 4 (Generator) áp dụng Programmatic Injection cực chuẩn: tách biệt rõ ràng [LLM Generated SQL] và [Pipeline Generated SQL] để so sánh, đồng thời không gây ảo giác."
    ],
    [
        "2",
        "2026年5月の会議の中で、「セキュリティ」について言及された会議の合計時間は何秒ですか？",
        "Trong các cuộc họp tháng 5, tổng thời gian các cuộc họp có nhắc đến 'bảo mật' là bao nhiêu giây?",
        "2026年5月の会議の中で、「セキュリティ」について言及された会議の合計時間は何秒ですか？",
        "sql",
        "partial",
        "Numeric SQL Pipeline & Ollama Qwen",
        "THÀNH CÔNG. Layer 1 xử lý xuất sắc Context-Aware Rewrite. Numeric Pipeline ở Layer 3 kết hợp thành công Heuristics + LLM để đẩy từ khóa 'security' vào Context Filter ($4) thay vì làm vỡ câu lệnh SQL."
    ],
    [
        "3",
        "それらの会議では、セキュリティのどんな問題について話し合われましたか？",
        "Trong các cuộc họp đó, những vấn đề bảo mật nào đã được thảo luận?",
        "2026年5月のセキュリティについて言及された会議では、セキュリティのどんな問題について話し合われましたか？",
        "rag",
        "partial",
        "RAG Engine (ChromaDB)",
        "THÀNH CÔNG TUYỆT ĐỐI. VẤN ĐỀ ĐÃ ĐƯỢC GIẢI QUYẾT: Lỗi History Bias (ảo giác format) đã biến mất. Nhờ việc chặn inject SQL prompt khi intent='rag' ở Layer 4, hệ thống không còn bịa ra các block SQL vô nghĩa. Lớp Memory dịch 'các cuộc họp đó' chuẩn xác."
    ],
    [
        "4",
        "2026年5月のすべての会議の中で、一番短い会議の時間は何秒でしたか？",
        "Trong tất cả các cuộc họp tháng 5, cuộc họp ngắn nhất kéo dài bao nhiêu giây?",
        "2026年5月のすべての会議の中で、一番短い会議の時間は何秒でしたか？",
        "sql",
        "full",
        "Numeric SQL Pipeline & Ollama Qwen",
        "THÀNH CÔNG XUẤT SẮC. VẤN ĐỀ ĐÃ ĐƯỢC GIẢI QUYẾT: Hệ thống Semantic Cache đã hoạt động chuẩn sau khi nâng threshold. Câu MIN() không còn bị nhầm với câu SUM() trước đó. Kiến trúc 4 lớp chạy mượt mà."
    ],
    [
        "5",
        "その一番短い会議で、どのような挨拶が交わされましたか？",
        "Trong cuộc họp ngắn nhất đó, mọi người đã chào hỏi nhau thế nào?",
        "2026年5月の最も短い会議でどのような挨拶が交わされましたか？",
        "rag",
        "partial",
        "RAG Engine (ChromaDB)",
        "THÀNH CÔNG XUẤT SẮC. VẤN ĐỀ ĐÃ ĐƯỢC GIẢI QUYẾT: Đồ thị tri thức (Neo4j Graph) ở Layer 2 phát huy sức mạnh tối đa. Nó phân giải đại từ 'その' (đó) thành ID của cuộc họp 25s, nhồi vào 'active_entities' giúp Layer 1 viết lại câu truy vấn hoàn hảo."
    ],
    [
        "6",
        "2026年5月の一つの会議あたりの平均時間は何秒ですか？",
        "Thời gian trung bình một cuộc họp trong tháng 5 là bao nhiêu giây?",
        "2026年5月の一つの会議あたりの平均時間は何秒ですか？",
        "sql",
        "full",
        "Numeric SQL Pipeline & Ollama Qwen",
        "THÀNH CÔNG XUẤT SẮC. Module SQL chứng minh được độ ổn định (Robustness) khi bắt chuẩn Intent AVG và sinh mã COALESCE(AVG(...), 0) an toàn không dính lỗi chia cho 0."
    ],
    [
        "7",
        "会議の中で、誰かが新しいソフトウェアの購入を提案した会議はありますか？",
        "Có cuộc họp nào có người đề xuất mua phần mềm mới không?",
        "会議の中で、新しいソフトウェアの購入を提案した会議はありますか？",
        "rag",
        "full",
        "RAG Engine (ChromaDB)",
        "THÀNH CÔNG XUẤT SẮC. Khả năng định tuyến (Router) cực kỳ nhạy bén: Không bị ép buộc theo luồng SQL đếm số lượng, hệ thống tự động nhảy sang RAG để lục tìm văn bản (Semantic Search)."
    ],
    [
        "8",
        "話題は変わりますが、DuckDuckGoで最新のAIトレンドについて検索して、簡単に教えてください。",
        "Đổi chủ đề nhé, hãy tìm xu hướng AI mới nhất trên DuckDuckGo và nói ngắn gọn cho tôi.",
        "最新のAIトレンドについて教えて",
        "web",
        "full",
        "Web Engine (DuckDuckGo Search)",
        "THÀNH CÔNG XUẤT SẮC. VẤN ĐỀ ĐÃ ĐƯỢC GIẢI QUYẾT: Khả năng chống nhiễu context (Context Wiping). Từ khoá '話題は変わりますが' (Đổi chủ đề) đã kích hoạt thành công tính năng xoá sạch Entity trong Graph DB, giúp hệ thống sang một scope hoàn toàn mới bằng Web Engine."
    ],
    [
        "9",
        "もし新しいAIソフトウェアが1500ドルだとしたら、現在の為替レートで日本円でいくらになりますか？",
        "Nếu phần mềm AI đó giá 1500 USD, thì tính theo tỷ giá hiện tại là bao nhiêu Yên Nhật?",
        "1500ドルは現在の為替レートで日本円でいくらになりますか?",
        "web",
        "full",
        "Web Engine (DuckDuckGo Search)",
        "THÀNH CÔNG XUẤT SẮC. Thể hiện sự liên kết liền mạch của Layer 3 (Planner). Thay vì ảo giác sinh SQL hoặc tìm RAG vô vọng, hệ thống tiếp tục dùng Web Engine để lấy tỷ giá realtime. Toàn bộ kiến trúc 4 lớp đã chứng minh tính khép kín và tự sửa lỗi hoàn thiện."
    ]
]

with open(csv_path, 'w', encoding='utf-8', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(headers)
    writer.writerows(data)

print(f"Đã tạo file đánh giá tổng thể hệ thống: {csv_path}")
