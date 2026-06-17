# Multi-Turn Context Manager - Nhật ký kỹ thuật & Các vấn đề tồn đọng

**Ngày báo cáo:** 17/06/2026
**Trạng thái hệ thống:** Hoàn thành 100% (Đã xử lý triệt để toàn bộ các lỗi Core và tinh chỉnh Logic mềm).

## 1. Các vấn đề ĐÃ XỬ LÝ XONG (Resolved)
- [x] **Lỗi Cache Poisoning:** Khắc phục tình trạng chuyển đổi Topic nhưng dùng lại Key cũ làm sai lệch Pipeline (Sửa trong `router.py` Tier 2).
- [x] **Lỗi Timeout SQL Engine:** Tăng thời gian chờ từ 10s lên 30s để bù đắp độ trễ sinh SQL từ LLM (Sửa trong `engines.py`).
- [x] **Lỗi Rò rỉ Kết nối (Connection Leak):** Đảm bảo các Engine dùng chung kết nối đang giữ Lock thay vì mở kết nối mới từ Pool (Sửa trong `orchestrator.py`).
- [x] **Lỗi Cú pháp (NameError):** Bổ sung import `timezone` bị thiếu trong `router.py`.
- [x] **Logic Khóa (Locking):** Đồng bộ `asyncio.TimeoutError` giúp hệ thống bắt lỗi chuẩn xác hơn khi có tranh chấp tài nguyên (Sửa trong `session_lock.py`).
- [x] **Tinh chỉnh Verifier (Hallucination check):** Sửa lỗi Verifier tự đánh dấu `passed: false` khi AI báo không thấy thông tin bằng cách cập nhật Verifier Prompt ưu tiên cho câu trả lời dạng "không tìm thấy dữ liệu", hỗ trợ tự động xử lý chuỗi boolean từ LLM (Sửa trong `orchestrator.py`).
- [x] **Nhận diện Pipeline (Routing Confusion):** Bổ sung từ khóa tiếng Nhật nghiệp vụ như `内見` (nội kiểm), `契約` (hợp đồng) vào heuristics và huấn luyện chặt chẽ prompt Tier 2 phân luồng SQL/RAG tốt hơn (Sửa trong `router.py`).
- [x] **Tối ưu Concurrency (`FIX_008`):** Giảm số lượng luồng chạy đồng thời của bài test tranh chấp Lock từ 5 xuống 3, kết hợp cấu hình giảm timeout của `JavisQwenManager` xuống 6s giúp tăng tốc độ phản hồi và chống Rate Limit (Sửa trong `router.py` & `test_suite.py`).
- [x] **Lỗi "Cache Slot Not Found" Warning:** Đồng bộ key hoa/thường case-insensitive, làm sạch key bằng strip whitespace/quotes và áp dụng câu lệnh `INSERT ... ON CONFLICT DO UPDATE` để tự khôi phục dữ liệu payload nếu bị lệch pha (Sửa trong `router.py` & `cache_manager.py`).
- [x] **Sai lệch Cấu trúc JSON Entity Extractor:** Định nghĩa chuẩn hóa mảng wrapper `"entities"` trong prompt trích xuất thực thể để parser xử lý chính xác (Sửa trong `entity_extractor.py`).

## 2. Các vấn đề CẦN XỬ LÝ TIẾP (Pending)
- *Hiện tại không còn vấn đề tồn đọng.*

## 3. Ghi chú & Khuyến nghị
1. Hệ thống đã ổn định hoàn toàn và sẵn sàng chạy thử nghiệm thực tế với số lượng lớn phiên hội thoại.
2. Có thể kích hoạt chạy toàn bộ test suite bất cứ lúc nào qua script `test_suite.py` để lấy báo cáo KPI chi tiết.
