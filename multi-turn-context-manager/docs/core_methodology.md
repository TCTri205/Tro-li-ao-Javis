# Phương pháp Thiết kế Cốt lõi (Core Methodology)

## So sánh các phương pháp Quản lý Ngữ cảnh Đa lượt

| Phương pháp | Mô tả | Ưu điểm | Nhược điểm | Đánh giá & Áp dụng |
| :--- | :--- | :--- | :--- | :--- |
| **1. Single-pass LLM Rewrite & Route** | Gửi toàn bộ lịch sử chat và truy vấn tới LLM để quyết định trong một lần. | ・Số lần gọi API ít (1 RTT). | ・Tiêu tốn lượng lớn token cho mỗi truy vấn.<br>・Độ trễ phát sinh khoảng 150-250ms. | Chỉ sử dụng như phương án dự phòng cho Tier 2. |
| **2. Multi-pass LLM (Split Task)** | Thực hiện "Viết lại truy vấn" và "Phân loại ý định" bằng các lần gọi LLM riêng biệt. | ・Giữ cho mỗi prompt đơn giản. | ・Số RTT tăng gấp đôi, độ trễ lớn hơn. | **Không sử dụng** (để tối ưu hóa độ trễ). |
| **3. Heuristic / Rule-based (Regex)** | Khớp từ khóa bằng biểu thức chính quy (Regular Expression). | ・Độ trễ gần như bằng 0.<br>・Chi phí token bằng 0. | ・Không xử lý được sự thay đổi ngữ cảnh phức tạp của ngôn ngữ tự nhiên. | Sử dụng làm bộ lọc bổ trợ cho Tier 1. |
| **4. 2-Tier Hybrid Routing (Fast/Slow Path)** | Kết hợp Tier 1 (Heuristic, Entity Lookup, pgvector) và Tier 2 (LLM Router). | ・Giảm tới 70% token định tuyến.<br>・Độ trễ trung bình của Fast Path dưới 15ms. | ・Cần quản lý chỉ mục thực thể (Entity Index) trong DB. | **Áp dụng chính thức** (để cân bằng giữa chi phí và tốc độ). |

## Tier 1: Cơ chế Lọc Nhanh (Fast Filtering)

Hệ thống kết hợp việc đối chiếu đại từ chỉ định (Entity Index Match) và khoảng cách ngữ nghĩa (pgvector Distance) để xác định câu hỏi mới của người dùng là "tiếp nối chủ đề cũ (Cache Hit)" hay "chuyển sang chủ đề mới (Topic Shift)".

### Bước 1: Đối chiếu thực thể nhanh (Entity linking)
*   Nếu truy vấn chứa các đại từ ("nó", "cái đó", "lúc nãy", "anh ấy", "そちら", "あちら", "同通話",...), hệ thống sẽ thực hiện tìm kiếm ARRAY trên bảng `session_entity_index`.
*   Nếu khớp với một thực thể duy nhất, hệ thống sẽ bỏ qua việc tính toán embedding và định tuyến ngay lập tức đến slot cache tương ứng.

### Bước 2: Khoảng cách Embedding ngữ nghĩa (pgvector Distance)
*   Sử dụng mô hình `multilingual-e5-small` để tạo vector $V_{new}$ cho truy vấn (timeout 1.0s).
*   **Vùng Xanh (Khoảng cách < 0.22 / Similarity > 0.78):** Xác định là cùng một chủ đề. Kích hoạt slot cache.
*   **Vùng Đỏ (Khoảng cách > 0.55 / Similarity < 0.45):** Xác định là chủ đề hoàn toàn khác. Thực hiện truy xuất mới (`needs_retrieval = "full"`).
*   **Vùng Xám:** Chuyển sang Tier 2 (LLM Router) để phân tích chi tiết hơn.

## Luồng Phản hồi Trực tiếp (Direct-Answer Path)

Để tránh lãng phí việc gọi các LLM lớn cho các đối chiếu thông tin đơn giản, bộ điều phối được tích hợp **Luồng Phản hồi Trực tiếp**. Luồng này bị vô hiệu hóa nếu `needs_retrieval == "partial"`.

| Pipeline | Định dạng dữ liệu | Điều kiện phản hồi trực tiếp | Luồng (Path) | Ví dụ |
| :--- | :--- | :--- | :--- | :--- |
| **SQL** | Dạng bảng (Rows) | Kết quả có đúng 1 dòng và $\le 3$ cột | **Direct Path** | "Thời gian gọi của GT_04?" -> "Thời gian gọi của GT_04 là 105 giây." |
| **WEB** | Đoạn trích (Snippet) | Chỉ có 1 kết quả và độ liên quan (relevance) > 0.85 | **Direct Path** | "Giá cổ phiếu Mitsubishi hôm nay?" -> Trả về snippet chứa giá cụ thể. |
| **WEB** | Đoạn trích (Snippet) | Nhiều kết quả hoặc độ liên quan thấp | **LLM Path** | LLM so sánh, tóm tắt nội dung và trả lời. |
| **RAG** | Đoạn văn bản | Mọi trường hợp | **LLM Path** | Cần hiểu ngữ cảnh và tạo câu trả lời tự nhiên, nên luôn dùng LLM. |

## Giải quyết nhanh bằng Chỉ mục Thực thể (Entity Index)

Thay vì xây dựng một Graph DB phức tạp như Neo4j, hệ thống sử dụng GIN Index và kiểu dữ liệu ARRAY của PostgreSQL để tăng tốc độ phân tích quy chiếu (Coreference Resolution).

1.  **Trích xuất:** Trích xuất các từ chỉ định từ truy vấn (ví dụ: "cái này", "việc đó", "người kia", "さっきのcall").
2.  **Tìm kiếm DB:** Sử dụng toán tử `@>` của PostgreSQL để quét nhanh mảng `display_names` liên kết với phiên hiện tại.
3.  **Ánh xạ:** Trả về ID slot khớp ngay lập tức cho bộ điều phối, giữ độ trễ dưới 3ms.

## Tự kiểm tra (Self-Check Verification)

Để ngăn chặn hiện tượng ảo giác (hallucination), hệ thống thực hiện **Tự kiểm tra** (Self-Check Verification) nhẹ sau khi tạo câu trả lời.

*   **Tối đa thử lại:** 2 lần (max_retries = 2).
*   **Đạt (Passed):** Nếu không mâu thuẫn với ngữ cảnh, trả lời ngay cho người dùng với độ tin cậy `high`.
*   **Thất bại (Failed):** Sau 2 lần thử lại vẫn mâu thuẫn, hệ thống trả về câu trả lời kèm cảnh báo disclaimer và đặt độ tin cậy `low`.
*   **Disclaimer:** "*(注意: この回答は自己検証で完全に一致しなかったため、信頼性が低くなっています。)*"
