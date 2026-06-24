import csv

csv_file = r"d:\javis_text2sql\hcacis\HCACIS_Production_Report.csv"

new_rows = [
    ["37", "2026年5月の会議の中で、「セキュリティ」について言及された会議の合計時間は何秒ですか？", "Tổng thời gian các cuộc họp trong tháng 5/2026 có nhắc đến 'bảo mật' là bao nhiêu giây?", "2026年5月の会議の中で、「セキュリティ」について言及された会議の合計時間は何秒ですか？", "sql", "full", "Numeric SQL Pipeline", "THÀNH CÔNG 70%. LLM nhận diện đúng intent và tự viết được câu lệnh SQL lọc LIKE '%セキュリティ%'. Tuy nhiên Pipeline bị thiếu logic xử lý keyword text nên không xuất ra được kết quả thực tế. LLM trả lời khéo léo thông báo không đủ data."],
    ["38", "それらの会議では、セキュリティのどんな問題について話し合われましたか？", "Trong các cuộc họp đó, những vấn đề bảo mật nào đã được thảo luận?", "2026年5月のセキュリティについて言及された会議では、セキュリティのどんな問題について話し合われましたか？", "rag", "partial", "ChromaDB Vector Search", "THÀNH CÔNG 80%. Định tuyến thành công, query viết lại rất chuẩn ('các cuộc họp có nhắc đến bảo mật...'). RAG không lấy được dữ liệu cụ thể do câu trên không có meeting cụ thể, nên LLM từ chối bịa đặt (Zero Hallucination)."],
    ["39", "会議の中で、誰かが新しいセキュリティソフトの購入を提案しましたか？", "Trong cuộc họp, có ai đề xuất mua phần mềm bảo mật mới không?", "会議の中で、新しいセキュリティソフトの購入について誰かが提案しましたか?", "rag", "partial", "ChromaDB Vector Search", "THÀNH CÔNG XUẤT SẮC. Kiểm tra Zero Hallucination (hỏi bẫy một thông tin không có thực). LLM trả lời tự tin là không tìm thấy thông tin mua phần mềm mới trong nội dung họp. Hoạt động kháng ảo giác rất chuẩn."],
    ["40", "2026年5月のすべての会議の中で、一番短い会議の時間は何秒でしたか？", "Trong tất cả các cuộc họp tháng 5/2026, cuộc họp ngắn nhất kéo dài bao nhiêu giây?", "2026年5月のすべての会議の中で、一番短い会議の時間は何秒でしたか？", "sql", "full", "Numeric SQL Pipeline", "THÀNH CÔNG XUẤT SẮC. Lấy được chính xác giá trị MIN là 25.0 giây. Pipeline SQL và LLM SQL sinh ra chính xác mệnh đề MIN."],
    ["41", "その一番短い会議で、どのような挨拶が交わされましたか？", "Trong cuộc họp ngắn nhất đó, mọi người đã chào hỏi nhau thế nào?", "2026年5月の最も短い会議でどのような挨拶が交わされましたか？", "rag", "partial", "ChromaDB Vector Search", "THÀNH CÔNG 90%. Trích xuất chính xác cuộc gọi lỡ dài 25s (ngày 6/5) và nêu đúng lời chào. Điểm trừ nhỏ: bị 'History Bias' tái phát, LLM học lỏm đoạn text [Pipeline Generated SQL] từ lượt trước để in ra (sẽ cần filter history)."],
    ["42", "話題を変えますが、現在の1米ドルは何円かインターネットで調べてください。", "Đổi chủ đề, hãy lên mạng tìm tỷ giá 1 USD hiện tại là bao nhiêu Yên.", "現在の1米ドルは何円か", "web", "full", "DuckDuckGo Search", "THÀNH CÔNG XUẤT SẮC. Lớp Web Search tự động kích hoạt và cào dữ liệu tỷ giá USD/JPY trực tiếp từ web (145-147 JPY) theo thời gian thực."],
    ["43", "もしセキュリティソフトが1500ドルだとしたら、日本円でいくらになりますか？", "Nếu phần mềm bảo mật giá 1500 USD, thì tính ra tiền Yên Nhật là bao nhiêu?", "1500ドルは日本円でいくらになりますか", "web", "full", "DuckDuckGo Search", "THÀNH CÔNG XUẤT SẮC. Thay vì bị đánh lừa là toán học Pure LLM, hệ thống đã nảy số gọi Web Engine để tìm công cụ đổi tiền trực tuyến '1500 USD to JPY' và ra kết quả xấp xỉ 219,825 Yên."]
]

with open(csv_file, 'a', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    writer.writerows(new_rows)

print("Appended 7 rows for Scenario 5.")
