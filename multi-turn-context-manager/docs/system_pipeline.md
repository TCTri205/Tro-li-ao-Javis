# Đường ống Hệ thống (System Pipeline)

Hệ thống quản lý ngữ cảnh đa lượt (multi-turn context management) hoạt động dựa trên một quy trình 8 bước nghiêm ngặt, đảm bảo tính nhất quán, hiệu suất và độ chính xác của câu trả lời.

## Luồng xử lý chi tiết

### 1. Tiếp nhận và Khóa phiên (Session Ingestion & Locking)
*   **Mô tả:** Hệ thống tiếp nhận truy vấn và xác lập quyền truy cập độc quyền cho phiên làm việc.
*   **Input:** `session_id`, `query`.
*   **Cơ chế:** Sử dụng *Advisory Lock* (PostgreSQL) dựa trên `session_id` để ngăn chặn các yêu cầu song song ghi đè dữ liệu ngữ cảnh trong cùng một phiên.
*   **Output:** Kết nối DB với giao dịch (transaction) đã được khóa.

### 2. Định tuyến 2 tầng (2-Tier Routing)
*   **Tầng 1 - Bộ lọc nhanh (Fast Filter):**
    *   Sử dụng heuristics (từ khóa chuyển đổi), tra cứu thực thể nhanh (Entity Index) và khoảng cách vector (`pgvector`) để kiểm tra xem có thể tái sử dụng bộ nhớ đệm (cache) hay không.
*   **Tầng 2 - Định tuyến LLM (LLM Router):**
    *   Kích hoạt khi Tầng 1 rơi vào "vùng xám" hoặc có sự mơ hồ. LLM sẽ phân tích 8 tin nhắn gần nhất và metadata của cache để đưa ra quyết định.
*   **Input:** `query`, `session_id`, lịch sử chat.
*   **Output:** `route_result` bao gồm:
    *   `rewritten_query`: Truy vấn đã được viết lại (giải quyết đại từ như "nó", "họ", "anh ấy").
    *   `target_pipeline`: SQL, RAG, WEB hoặc MODEL.
    *   `needs_retrieval`: `none` (dùng cache), `partial` (lấy thêm), hoặc `full` (truy xuất mới).
    *   `target_topic_key`: Khóa định danh chủ đề hiện tại.

### 3. Thực thi và Truy xuất (Execution & Retrieval)
*   **Mô tả:** Dựa trên quyết định định tuyến, hệ thống thực thi các công cụ tương ứng.
*   **Input:** `target_pipeline`, `rewritten_query`, `partial_fetch_params`.
*   **Cơ chế bảo vệ & tối ưu:**
    *   **Circuit Breaker:** Mỗi engine được bọc bởi bộ ngắt mạch. Nếu thất bại liên tiếp > 3 lần, engine sẽ tạm dừng (Open state) trong 30 giây để tránh làm treo hệ thống, tự động fallback sang kiến thức nội tại (Parametric Knowledge).
    *   **Heuristic SQL Translation:** Các câu hỏi phổ biến về thời gian, người tham gia, tóm tắt của 1 GT cụ thể được dịch trực tiếp sang SQL bằng Regex để bỏ qua độ trễ của LLM.
*   **Các kịch bản:**
    *   **Cache Hit:** Lấy trực tiếp `payload` từ bảng `session_context_payload`.
    *   **Partial Fetch:** Chạy Engine với tham số lọc bổ sung, sau đó hợp nhất (merge) kết quả mới vào `payload` cũ.
    *   **Full Retrieval:** Chạy mới hoàn toàn các Engine (SQL Engine, RAG Engine, hoặc Web Engine).
*   **Output:** `payload` (Dữ liệu thô JSON).

### 4. Trích xuất Thực thể và metadata (Entity Indexing & Summary)
*   **Mô tả:** Phân tích dữ liệu thô để xây dựng bản đồ thực thể cho các lượt hội thoại sau.
*   **Input:** `payload`, `target_pipeline`, `rewritten_query`.
*   **Cơ chế:** 
    *   Trích xuất `entity_id`, `entity_type`, `display_names` (các tên gọi khác nhau của thực thể).
    *   Tự động liên kết các đại từ chỉ định ("cái này", "hợp đồng đó") với thực thể thực tế.
    *   Xây dựng `summary_context` (tóm tắt ngắn gọn nội dung cache) để lưu vào bảng "Hot".
*   **Output:** Cập nhật bảng `session_entity_index`.

### 5. Cập nhật Bộ nhớ đệm (Cache Orchestration)
*   **Mô tả:** Lưu trữ trạng thái mới nhất của cuộc hội thoại.
*   **Input:** `payload`, `summary_context`, `query_embedding`.
*   **Cơ chế:** Sử dụng chiến lược LRU (Least Recently Used) - mỗi phiên chỉ giữ tối đa 3 slot cache chủ đề để tối ưu tài nguyên.
*   **Output:** ID cache slot đã được cập nhật hoặc tạo mới.

### 6. Tạo câu trả lời (Answer Generation - Dual Path)
*   **Đường dẫn Trực tiếp (Direct Path):** Dành cho dữ liệu đơn giản (ví dụ: SQL chỉ trả về 1 dòng), hệ thống dùng template để trả lời ngay mà không cần qua LLM lần 2.
*   **Đường dẫn LLM (LLM Path):** Sử dụng LLM để đọc hiểu ngữ cảnh (`payload`) và `summary_context` để tạo câu trả lời tự nhiên bằng tiếng Việt/Nhật.
*   **Input:** `payload`, `rewritten_query`, `summary_context`.
*   **Output:** `answer`, `answer_confidence`.

### 7. Xác minh tự thân (Self-Check Verification)
*   **Mô tả:** Ngăn chặn ảo giác (hallucination).
*   **Input:** `answer`, `payload` (dữ liệu thô).
*   **Cơ chế:** Một quy trình LLM Verifier độc lập sẽ đối chiếu câu trả lời với dữ liệu thô. Nếu phát hiện sai sót, hệ thống sẽ yêu cầu tái tạo câu trả lời (tối đa 2 lần thử lại).
*   **Output:** Trạng thái `self_check_passed`.

### 8. Ghi nhật ký và Hoàn tất (Logging & Commit)
*   **Mô tả:** Lưu trữ lịch sử và giải phóng tài nguyên.
*   **Input:** Tất cả metadata của quá trình xử lý.
*   **Output:** 
    *   Lưu vào bảng `chat_history`.
    *   Commit giao dịch DB.
    *   Giải phóng Session Lock.
    *   Trả kết quả cuối cùng cho người dùng.
