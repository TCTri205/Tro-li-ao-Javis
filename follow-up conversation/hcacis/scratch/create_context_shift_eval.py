import csv

csv_path = r'd:\javis_text2sql\hcacis\HCACIS_Context_Shift_Evaluation.csv'

headers = [
    "Turn", 
    "Nhóm Ngữ Cảnh (Context Group)", 
    "Câu hỏi gốc", 
    "Câu hỏi đã Rewrite (Coreference Resolved)", 
    "Engine / Intent", 
    "Đánh giá chi tiết (Evaluation) & Graph DB Performance"
]

data = [
    [
        "1",
        "Group A: Cuộc họp 15/5",
        "2026年5月15日の会議では、主にどんな内容が話し合われましたか？",
        "2026年5月15日の会議では、主にどんな内容が話し合われましたか？",
        "RAG Engine",
        "THÀNH CÔNG. Khởi tạo Context Group A. Hệ thống nhận diện đúng intent_category='rag'. Đưa cuộc họp 15/5 vào Graph DB. Trả lời lịch sự không tìm thấy thông tin (Không bị ảo giác)."
    ],
    [
        "2",
        "Group A: Cuộc họp 15/5",
        "その会議の中で、「山田さん」は何回発言しましたか？",
        "2026年5月15日の会議の中で、山田さんは何回発言しましたか？",
        "Numeric SQL (Groq+Qwen)",
        "THÀNH CÔNG TUYỆT ĐỐI. Graph DB phân giải chữ 'その会議' (cuộc họp đó) chuẩn xác thành 'cuộc họp ngày 15/5'. Pipeline đếm số lần phát ngôn của Yamada chính xác bằng câu SQL COUNT."
    ],
    [
        "3",
        "Group B: Web Search (Sony)",
        "話題は変わりますが、日本の「ソニー」の最新ニュースをインターネットで調べて。",
        "ソニー最新ニュース",
        "Web Engine (DuckDuckGo)",
        "THÀNH CÔNG. Nhận diện từ khoá '話題は変わりますが' (Chuyển chủ đề). Hệ thống chuyển `is_followup=False` để bypass các Entity cũ, giúp Web Search tìm kiếm chính xác tin tức về Sony không bị nhiễu."
    ],
    [
        "4",
        "Group B: Web Search (Sony)",
        "その会社のCEOは現在誰ですか？",
        "ソニーの現在のCEOは誰ですか？",
        "Web Engine (DuckDuckGo)",
        "THÀNH CÔNG XUẤT SẮC. Mặc dù là Web Engine, Graph Memory vẫn hoạt động chéo. Nó phân giải 'その会社' (công ty đó) thành 'Sony' dựa trên lịch sử tìm kiếm ở Turn 3 và lấy ra kết quả chính xác."
    ],
    [
        "5",
        "Quay lại Group A",
        "先ほどの5月15日の会議の話に戻りますが、山田さんの発言の平均時間はどれくらいでしたか？",
        "5月15日の会議における山田さんの発言の平均時間はどれくらいでしたか？",
        "Numeric SQL (Groq+Qwen)",
        "THÀNH CÔNG TUYỆT ĐỐI. Dù bị ngắt quãng bởi 2 lượt tìm kiếm Web, hệ thống Graph Memory vẫn giữ nguyên vẹn Entity 15/5. Kéo lại ngữ cảnh cũ hoàn hảo và tính trung bình (AVG) chính xác."
    ],
    [
        "6",
        "Group C: Cuộc họp ngắn nhất",
        "2026年5月のすべての会議の中で、一番短い会議の時間は何秒でしたか？",
        "2026年5月のすべての会議の中で、一番短い会議の時間は何秒でしたか？",
        "Numeric SQL (Groq+Qwen)",
        "THÀNH CÔNG. Khởi tạo Context Group C. Intent 'sql' sử dụng hàm MIN() thành công và gán 'cuộc họp ngắn nhất' làm Entity mới nhất trong đồ thị tri thức (Graph DB)."
    ],
    [
        "7",
        "Group C: Cuộc họp ngắn nhất",
        "その会議ではどんな結論が出ましたか？",
        "2026年5月の最も短い会議ではどんな結論が出ましたか？",
        "RAG Engine",
        "THÀNH CÔNG. Phân giải đại từ 'その会議' thành 'cuộc họp ngắn nhất tháng 5/2026'. Router điều hướng chính xác về RAG để tìm kiếm văn bản."
    ],
    [
        "8",
        "Group D: Pure LLM Bypass",
        "今の結論を箇条書きで3つのポイントに要約して英語に翻訳してください。",
        "現在の結論を箇条書きで3つのポイントに要約して英語に翻訳してください。",
        "Pure LLM (Bypass DB)",
        "THÀNH CÔNG XUẤT SẮC. Layer 1 phân loại chuẩn xác ý định xử lý ngôn ngữ thuần túy (`pure_llm`). Tiết kiệm tài nguyên Database. LLM Qwen lấy bối cảnh hội thoại để tóm tắt và dịch tiếng Anh hoàn hảo."
    ],
    [
        "9",
        "Quay lại Group C",
        "その一番短い会議で、誰かが挨拶をしましたか？",
        "2026年5月の最も短い会議で、誰かが挨拶をしましたか？",
        "RAG Engine",
        "THÀNH CÔNG TUYỆT ĐỐI. Sau một lượt Pure LLM Dịch thuật đầy biến động, Graph Memory vẫn nhớ rõ '一番短い会議' (Cuộc họp ngắn nhất) là gì để nhét ngược lại vào câu truy vấn RAG."
    ],
    [
        "10",
        "Quay lại Group A",
        "最後にもう一度確認しますが、5月15日の会議の合計時間は何秒でしたか？",
        "5月15日の会議の合計時間は何秒でしたか？",
        "Numeric SQL (Groq+Qwen)",
        "THÀNH CÔNG XUẤT SẮC. Nhảy vọt từ Group C về tận Group A đầu tiên. Hệ thống tính SUM chính xác. Minh chứng hùng hồn nhất cho việc Graph Memory bảo lưu toàn bộ dấu vết các đối tượng xuyên suốt 1 Session."
    ]
]

with open(csv_path, 'w', encoding='utf-8', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(headers)
    writer.writerows(data)

print(f"Đã tạo file đánh giá chuyển đổi ngữ cảnh: {csv_path}")
