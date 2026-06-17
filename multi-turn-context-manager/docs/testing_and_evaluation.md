# Kiểm thử và Đánh giá (Testing & Evaluation)

## Cấu trúc bài kiểm tra Benchmark

Để đánh giá khách quan hiệu năng của hệ thống, chúng tôi thực hiện các bài kiểm tra tự động bằng `test_suite.py`.

### 1. Danh mục đánh giá

*   **Standard (Kịch bản tiêu chuẩn):** Kiểm tra việc tiếp tục, chuyển đổi và quay lại chủ đề trong luồng trò chuyện tự nhiên.
*   **NEG (Kịch bản tiêu cực/phức tạp):**
    *   Giải quyết các đại từ mơ hồ.
    *   Chuyển đổi chủ đề đột ngột.
    *   Thời gian chờ (timeout) của bộ định tuyến hoặc embedding.
    *   Kiểm tra hành vi loại bỏ dữ liệu của LRU cache.
*   **FIX (Kịch bản khôi phục/sửa lỗi):**
    *   Tự động dự phòng (fallback) khi thất bại embedding.
    *   Sửa lỗi ảo giác thông qua tự kiểm tra (Self-Check).
    *   Hành vi của khóa cố vấn (advisory lock) khi có các yêu cầu song song.

### 2. Các chỉ số đánh giá chính (KPI)

*   **Độ trễ trung bình (Average Latency):** Thời gian từ khi yêu cầu đến khi có câu trả lời. Chỉ số này sẽ giảm khi tỷ lệ Fast Path (Tier 1) tăng lên.
*   **Tỷ lệ Hit Cache (Cache Hit Rate):** Tỷ lệ các trường hợp đạt `needs_retrieval = none`.
*   **Độ chính xác câu trả lời (Answer Accuracy):** Tỷ lệ các trường hợp vượt qua bước tự kiểm tra (Self-Check).
*   **Phân tích định tuyến (Routing Breakdown):** Tỷ lệ sử dụng của từng phương pháp định tuyến (Heuristics, Embeddings, LLM Router).

### 3. Cách thực hiện kiểm thử

Chạy lệnh sau để tạo báo cáo benchmark:

```bash
python tests/test_suite.py
```

Báo cáo xuất ra sẽ bao gồm chi tiết về độ trễ p95/p99, tỷ lệ sử dụng cache và chi tiết các trường hợp kiểm thử bị thất bại.
