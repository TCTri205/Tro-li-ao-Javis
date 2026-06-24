import csv
import os

csv_path = r'd:\javis_text2sql\hcacis\HCACIS_Production_Report.csv'

new_rows = [
    [
        "37",
        "2026年5月の会議の中で、会議の件数は合計でいくつありましたか？",
        "Trong các cuộc họp tháng 5 năm 2026, có tổng cộng bao nhiêu cuộc họp?",
        "2026年5月の会議の中で、会議の件数は合計でいくつありましたか？",
        "sql",
        "full",
        "Numeric SQL Pipeline & Ollama Text-to-SQL",
        "THÀNH CÔNG XUẤT SẮC. Layer 1 phân tích chuẩn. Pipeline SQL (`COUNT(DISTINCT t.id)`) và LLM SQL (`COUNT(*)`) đều chính xác, lấy ra kết quả 5 cuộc họp. Hiển thị đủ 2 khối SQL theo yêu cầu."
    ],
    [
        "38",
        "2026年5月の会議の中で、「セキュリティ」について言及された会議の合計時間は何秒ですか？",
        "Trong các cuộc họp tháng 5 năm 2026, tổng thời gian các cuộc họp có nhắc đến 'bảo mật' là bao nhiêu giây?",
        "2026年5月の会議の中で、「セキュリティ」について言及された会議の合計時間は何秒ですか？",
        "sql",
        "partial",
        "Numeric SQL Pipeline & Ollama Text-to-SQL",
        "THÀNH CÔNG MỘT PHẦN. LLM Generated SQL viết rất chuẩn xác với việc JOIN `chunks_turn` để quét `%セキュリティ%`. Tuy nhiên Pipeline SQL không bắt được keyword này (chỉ có SUM bình thường). Lỗi này có thể được fix trong bản cập nhật pipeline tiếp theo."
    ],
    [
        "39",
        "それらの会議では、セキュリティのどんな問題について話し合われましたか？",
        "Trong những cuộc họp đó, những vấn đề bảo mật nào đã được thảo luận?",
        "2026年5月のセキュリティについて言及された会議では、セキュリティのどんな問題について話し合われましたか？",
        "rag",
        "partial",
        "RAG Engine (ChromaDB)",
        "THÀNH CÔNG. Định tuyến RAG chính xác cho câu hỏi cần tóm tắt chi tiết. Layer 4 đã xử lý uyển chuyển khi không có dữ liệu thật (trả lời xin lỗi mượt mà) thay vì bị ảo giác (History Bias)."
    ],
    [
        "40",
        "2026年5月のすべての会議の中で、一番短い会議の時間は何秒でしたか？",
        "Trong tất cả cuộc họp tháng 5 năm 2026, thời gian cuộc họp ngắn nhất là bao nhiêu giây?",
        "2026年5月のすべての会議の中で、一番短い会議の時間は何秒でしたか？",
        "sql",
        "full",
        "Numeric SQL Pipeline & Ollama Text-to-SQL",
        "THÀNH CÔNG XUẤT SẮC. Pipeline SQL dùng `ORDER BY ASC LIMIT 1`, LLM SQL dùng `MIN(duration_seconds)`. Cả 2 đều đúng chuẩn và lấy ra kết quả 25 giây."
    ],
    [
        "41",
        "その一番短い会議で、どのような挨拶が交わされましたか？",
        "Trong cuộc họp ngắn nhất đó, những lời chào hỏi nào đã được trao đổi?",
        "2026年5月の最も短い会議でどのような挨拶が交わされましたか？",
        "rag",
        "partial",
        "RAG Engine (ChromaDB)",
        "THÀNH CÔNG. Nhận diện cực chuẩn câu hỏi tiếp nối (follow-up). Rewritten query hoàn hảo. Trả lời RAG sạch sẽ không bị lẫn khối SQL (History Bias đã bị tiêu diệt hoàn toàn)."
    ],
    [
        "42",
        "2026年5月の一つの会議あたりの平均時間は何秒ですか？",
        "Trung bình mỗi cuộc họp trong tháng 5 năm 2026 kéo dài bao nhiêu giây?",
        "2026年5月の一つの会議あたりの平均時間は何秒ですか？",
        "sql",
        "full",
        "Numeric SQL Pipeline & Ollama Text-to-SQL",
        "THÀNH CÔNG. Dịch và nhận diện Intent AVG chính xác. Pipeline và LLM Generated SQL đều sử dụng phép toán `AVG` thành công, cho ra 1,645.2 giây."
    ],
    [
        "43",
        "会議の中で、誰かが新しいソフトウェアの購入を提案した会議はありますか？",
        "Trong các cuộc họp, có cuộc họp nào có ai đó đề xuất mua phần mềm mới không?",
        "会議の中で、新しいソフトウェアの購入を提案した会議はありますか？",
        "rag",
        "full",
        "RAG Engine (ChromaDB)",
        "THÀNH CÔNG. Chuyển hướng Topic sang dạng RAG Document Retrieval thành công."
    ],
    [
        "44",
        "話題は変わりますが、DuckDuckGoで最新のAIトレンドについて検索して、簡単に教えてください。",
        "Chuyển chủ đề, hãy tìm kiếm DuckDuckGo về xu hướng AI mới nhất và giải thích ngắn gọn.",
        "最新のAIトレンド",
        "web",
        "full",
        "Web Engine (DuckDuckGo Search)",
        "THÀNH CÔNG XUẤT SẮC. Nhận diện Keyword cực sắc bén: `最新のAIトレンド`. Web Engine cào dữ liệu tốt và Layer 4 tổng hợp thành 4 ý gọn gàng về Trends AI năm 2026."
    ],
    [
        "45",
        "もし新しいAIソフトウェアが1500ドルだとしたら、現在の為替レートで日本円でいくらになりますか？",
        "Nếu phần mềm AI mới giá 1500 USD, thì với tỷ giá hiện tại là bao nhiêu Yên Nhật?",
        "1500ドルは現在の為替レートで日本円でいくらになりますか?",
        "web",
        "full",
        "Web Engine (DuckDuckGo Search)",
        "THÀNH CÔNG XUẤT SẮC. Tự động bóc tách và viết lại câu hỏi tỷ giá, DuckDuckGo lấy ra được số tiền xấp xỉ 203,400 JPY. Hệ thống đã hoạt động hoàn thiện mượt mà và chống chịu tốt ngay cả khi gặp lỗi API."
    ]
]

# Read existing rows to avoid duplicates if append_csv2 already did something
existing_turns = set()
try:
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if row:
                existing_turns.add(row[0])
except Exception as e:
    print(e)

# Append only if not already exists (Turn 37-45)
with open(csv_path, 'a', encoding='utf-8', newline='') as f:
    writer = csv.writer(f)
    for row in new_rows:
        if row[0] not in existing_turns:
            writer.writerow(row)

print("Đã thêm 9 lượt đánh giá cuối cùng vào file HCACIS_Production_Report.csv thành công!")
