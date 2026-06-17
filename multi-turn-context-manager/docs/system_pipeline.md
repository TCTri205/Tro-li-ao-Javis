# Đường ống Hệ thống (System Pipeline)

## Luồng tổng thể

Hệ thống xử lý truy vấn của người dùng và tạo ra câu trả lời tối ưu thông qua các đường ống (pipeline) sau:

### 1. Tiếp nhận và Khóa (Ingestion & Locking)
*   Nhận truy vấn từ người dùng và lấy khóa cố vấn (advisory lock) dựa trên ID phiên. Việc này giúp ngăn chặn xử lý song song trong cùng một phiên.

### 2. Định tuyến (Routing)
*   **Tier 1:** Xác định bộ nhớ đệm (cache) thông qua khớp biểu thức chính quy nhanh, tìm kiếm thực thể hoặc độ tương đồng vector.
*   **Tier 2:** Trong trường hợp ngữ cảnh phức tạp hoặc truy vấn mơ hồ, LLM sẽ phân tích lịch sử, viết lại truy vấn và chọn đường ống phù hợp.

### 3. Thực thi và Truy xuất (Execution & Retrieval)
*   **Cache Hit:** Lấy dữ liệu từ bộ nhớ đệm hiện có.
*   **Partial Fetch:** Lấy thêm các thông tin cụ thể bổ sung vào ngữ cảnh hiện có và hợp nhất chúng.
*   **Full Retrieval:** Truy xuất dữ liệu từ SQL, RAG hoặc WEB như một chủ đề mới.

### 4. Trích xuất thực thể (Entity Extraction)
*   Trích xuất các thực thể chính (tên người, tài liệu, phiên gọi điện, v.v.) từ dữ liệu đã lấy và lập chỉ mục chúng bằng cách liên kết với các đại từ chỉ định.

### 5. Tạo câu trả lời (Answer Generation)
*   **Direct Path:** Đối với dữ liệu đơn giản, câu trả lời được tạo ngay lập tức bằng các mẫu đã định nghĩa trước.
*   **LLM Path:** Đối với dữ liệu phức tạp, LLM sẽ đọc hiểu ngữ cảnh và tạo câu trả lời bằng tiếng Việt tự nhiên.

### 6. Xác minh (Verification)
*   LLM tự kiểm tra xem câu trả lời được tạo ra có dựa trên dữ liệu đã cung cấp hay không và có chứa thông tin sai lệch nào không.

### 7. Phản hồi và Ghi nhật ký (Response & Logging)
*   Gửi câu trả lời cho người dùng, lưu trữ thông tin thống kê định tuyến và lịch sử vào cơ sở dữ liệu để hoàn tất giao dịch.
