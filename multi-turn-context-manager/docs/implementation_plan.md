# Kế hoạch Triển khai (Implementation Plan)

## Giai đoạn 1: Xây dựng nền tảng và Khởi tạo lược đồ

1.  **Thiết lập môi trường PostgreSQL:** Chuẩn bị một thực thể PostgreSQL đã kích hoạt tiện ích mở rộng `pgvector`.
2.  **Áp dụng lược đồ:** Chạy tệp `init_db.py` để xây dựng các bảng cho bộ nhớ đệm, chỉ mục thực thể và lịch sử trò chuyện.
3.  **Di chuyển dữ liệu:** Sử dụng `migrate_transcripts.py` để chuyển đổi các `session_id` hiện có sang định dạng chuẩn hóa (ví dụ: `GT_01`).

## Giai đoạn 2: Triển khai logic định tuyến (Routing)

1.  **Xây dựng bộ định tuyến Tier 1:** Triển khai `router.py` bao gồm các biểu thức chính quy (Regex) và trình bao bọc `_safe_embed`.
2.  **Chuẩn bị danh sách đại từ:** Thêm các từ chỉ định thường gặp trong ngữ cảnh kinh doanh (ví dụ: "vụ đó", "lúc nãy", "anh ấy",...) vào danh sách PRONOUNS.
3.  **Điều chỉnh Tier 2:** Thiết lập prompt cho LLM có khả năng hiểu ngữ cảnh tốt để tăng cường bổ sung các đại từ chỉ định.

## Giai đoạn 3: Engine thực thi và Điều phối (Orchestration)

1.  **Triển khai các Engine:** Xây dựng các công cụ SQL, RAG, Web Search và thiết lập system prompt tương ứng.
2.  **Tích hợp Orchestrator:** Xây dựng `orchestrator.py` để kiểm soát vòng đời 8 bước và tích hợp cơ chế khóa cố vấn (advisory lock).
3.  **Xác định luồng phản hồi trực tiếp:** Thiết lập các mẫu phản hồi để cho phép trả lời nhanh chóng.

## Giai đoạn 4: Kiểm chứng và Đánh giá

1.  **Xây dựng bộ kiểm thử (Test Suite):** Triển khai các kịch bản kiểm thử trong `test_suite.py`.
2.  **Kích hoạt tính năng tự kiểm tra:** Triển khai prompt kiểm tra hiện tượng ảo giác (hallucination check) sau khi tạo câu trả lời.
3.  **Thực hiện Benchmark:** Đo lường độ trễ và tỷ lệ hit cache, đồng thời thực hiện các tinh chỉnh nhỏ đối với các ngưỡng (threshold).
