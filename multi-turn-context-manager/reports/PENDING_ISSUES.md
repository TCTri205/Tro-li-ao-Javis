# Multi-Turn Context Manager - Nhật ký kỹ thuật & Các vấn đề tồn đọng

**Ngày báo cáo:** 15/06/2026
**Trạng thái hệ thống:** Đang hoàn thiện (Đã xử lý xong các lỗi nghiêm trọng về Core, đang tinh chỉnh Logic "mềm").

## 1. Các vấn đề ĐÃ XỬ LÝ XONG (Resolved)
- [x] **Lỗi Cache Poisoning:** Khắc phục tình trạng chuyển đổi Topic nhưng dùng lại Key cũ làm sai lệch Pipeline (Sửa trong `router.py` Tier 2).
- [x] **Lỗi Timeout SQL Engine:** Tăng thời gian chờ từ 10s lên 30s để bù đắp độ trễ sinh SQL từ LLM (Sửa trong `engines.py`).
- [x] **Lỗi Rò rỉ Kết nối (Connection Leak):** Đảm bảo các Engine dùng chung kết nối đang giữ Lock thay vì mở kết nối mới từ Pool (Sửa trong `orchestrator.py`).
- [x] **Lỗi Cú pháp (NameError):** Bổ sung import `timezone` bị thiếu trong `router.py`.
- [x] **Logic Khóa (Locking):** Đồng bộ `asyncio.TimeoutError` giúp hệ thống bắt lỗi chuẩn xác hơn khi có tranh chấp tài nguyên (Sửa trong `session_lock.py`).

## 2. Các vấn đề CẦN XỬ LÝ TIẾP (Pending)

### A. Tinh chỉnh Verifier (Bộ kiểm tra Hallucination)
- **Vấn đề:** Verifier đang bị "rối loạn" giữa việc đánh giá đúng sai và tuân thủ format. Dù trong text nó khẳng định AI trả lời đúng (khi báo không thấy thông tin), nhưng trong trường JSON nó vẫn trả về `"passed": false`.
- **Giải pháp:** Tái cấu trúc lại Prompt của Verifier trong `orchestrator.py`, đưa quy tắc ưu tiên cho các câu trả lời "không tìm thấy dữ liệu" lên hàng đầu và sử dụng ngôn ngữ ép buộc mạnh hơn.

### B. Cải thiện Nhận diện Pipeline (Routing Confusion)
- **Vấn đề:** Một số câu hỏi mang tính nghiệp vụ cao (như "nội kiểm" - 内見) vẫn bị Router ném vào pipeline `MODEL` thay vì `SQL/RAG`.
- **Giải pháp:** 
    - Cập nhật danh sách từ khóa Heuristic trong `router.py` để bao quát các thuật ngữ nghiệp vụ đặc thù.
    - Tăng cường chỉ dẫn trong System Prompt của Tier 2 để LLM ưu tiên SQL/RAG cho mọi câu hỏi liên quan đến dữ liệu lịch sử.

### C. Tối ưu Test Concurrency (`FIX_008`)
- **Vấn đề:** Bài test chạy 5 request song song bị Timeout Lock (120 giây vẫn không đủ) do API bị chậm/hết limit làm tiến trình xử lý kéo dài quá mức.
- **Giải pháp:** 
    - Tối ưu hóa tốc độ của `JavisQwenManager` (giảm timeout nội bộ).
    - Cân nhắc tăng thời gian chờ trong `test_suite.py` hoặc chạy test với số lượng luồng nhỏ hơn.

### D. Xử lý "Cache Slot Not Found" Warning
- **Vấn đề:** Đôi khi Router (Tier 1) báo trúng Cache (Hit) dựa trên Vector, nhưng khi vào DB tìm `topic_key` thì không thấy.
- **Giải pháp:** Kiểm tra tính đồng bộ giữa việc tạo `topic_key` của LLM Tier 2 và việc lưu vào Postgres. Đảm bảo key không bị cắt tỉa hoặc đổi định dạng giữa chừng.

## 3. Ghi chú cho buổi làm việc tiếp theo
1. Tập trung sửa Prompt cho `_verify_hallucination` trong `orchestrator.py`.
2. Mở rộng từ khóa nghiệp vụ trong `router.py`.
3. Chạy lại bài test `NEG_016` và `SCENARIO_2_T3` để kiểm chứng.
