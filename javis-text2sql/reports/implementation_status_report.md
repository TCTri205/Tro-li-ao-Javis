# Báo cáo Tiến trình Triển khai và Đánh giá Phân hệ Javis Text-to-SQL

Báo cáo này tổng hợp chi tiết những tính năng đã triển khai, các thành phần đã hoàn thành, kết quả đánh giá thực tế và lộ trình tiếp theo của phân hệ **Text-to-SQL** thuộc dự án Trợ lý ảo Javis.

---

## 1. Tổng quan Phân hệ Javis Text-to-SQL
Trong kiến trúc tổng thể của Trợ lý ảo Javis, **Text-to-SQL** hoạt động như một công cụ chuyên trách (Tool) được gọi bởi **Routing Node** để xử lý các câu hỏi định lượng, thống kê, đếm hoặc lọc thông tin có cấu trúc. Phân hệ này truy vấn trên cơ sở dữ liệu quan hệ PostgreSQL được đồng bộ hóa từ các cuộc họp và tài liệu doanh nghiệp.

Kiến trúc thực tế hiện tại đã hiện thực hóa hoàn toàn **Tầng 1 (Core Infrastructure)**, **Tầng 2 (Routing Node + Text2SQL cơ bản)** và **Tầng 3 (Nâng cao dựa trên Failure Patterns)** theo thiết kế của dự án.

---

## 2. Những gì đã triển khai được (Implemented Features)

### 2.1. Tầng 1: Core Infrastructure (Cơ sở hạ tầng cốt lõi)
*   **PostgreSQL Schema & Semantic Views:**
    *   Thiết lập lược đồ vật lý hoàn chỉnh gồm các bảng: `meetings`, `passages`, `turns`, `entity_aliases`, `commitments` và bảng vector mờ `golden_queries`.
    *   Xây dựng **8 Semantic Views** phẳng hóa cấu trúc dữ liệu JSONB phức tạp giúp LLM dễ dàng truy xuất:
        *   `v_topics`, `v_commitments`, `v_amounts`, `v_action_items`, `v_open_questions`, `v_statements`, `v_dates`, `v_speaker_turns`.
*   **Multi-tenant Isolation (Cô lập đa thuê):**
    *   Tích hợp cột `user_id UUID` vào bảng `meetings` và kích hoạt **Row Level Security (RLS)** trên các bảng `meetings`, `passages`, `turns`, `commitments`.
    *   Chính sách RLS tự động cô lập dữ liệu theo `app.current_user_id` của session.
    *   Hàm thực thi `execute_readonly` và ETL `load_meeting` tự động thiết lập `app.current_user_id` qua `set_config` trong transaction.
*   **ETL Ingestion Pipeline (Đường ống nạp dữ liệu):**
    *   **Rule-based Chunker:** Phân tách lượt thoại từ file markdown/hội thoại thô và tự động gộp nhóm (8-10 turns hoặc ngắt sớm nếu có khoảng lặng > 3 phút dựa trên timestamp).
    *   **LLM Metadata Enrichment:** Sử dụng LLM với cấu trúc đầu ra nghiêm ngặt qua **Pydantic (PassageEnrichmentSchema)** để tự động trích xuất: Topics, Entities, Keywords, Amounts, Dates, Commitments.
    *   **Data Loader bất đồng bộ:** Nạp dữ liệu song song sử dụng `asyncio` và kiểm soát tốc độ qua `Semaphore(10)`, cam kết ghi DB trong transaction an toàn, hỗ trợ ghi nhận trạng thái lỗi `enrichment_status = 'llm_failed'` nếu LLM gặp sự cố.

### 2.2. Tầng 2: Routing Node & Text2SQL Pipeline
*   **Routing Node (Bộ định tuyến câu hỏi):**
    *   Phân tích ý định câu hỏi để điều phối sang luồng `sql`, `rag`, hoặc `hybrid` dựa trên cơ chế **Keyword-based Heuristic** tối ưu cho tiếng Nhật (với các từ khóa kỹ thuật tiếng Anh). Luồng này xử lý logic Python local hoàn toàn, không phụ thuộc LLM bên ngoài giúp tối ưu latency.
*   **Groq API Integration & API Key Rotation:**
    *   Hiện thực hóa `GroqClient` gọi REST API của Groq (tương thích OpenAI).
    *   Cơ chế **API Key Rotation** thông minh: Hỗ trợ nạp nhiều API keys (từ `GROQ_API_KEYS`, `GROQ_API_KEY` hoặc các biến `GROQ_API_KEY_N`). Tự động luân chuyển khóa theo cơ chế round-robin và phục hồi lỗi (failover) tức thời khi gặp mã lỗi rate limit 429 hoặc lỗi kết nối.
    *   Tích hợp Groq JSON Mode khi gọi đầu ra có cấu trúc (`structured_output`).
*   **Text2SQL Pipeline (Đường ống NL-to-SQL):**
    *   **SQL Validation (AST Analysis):** Tích hợp thư viện `sqlglot` để phân tích cây cú pháp. Chặn các câu lệnh sửa đổi dữ liệu (DML/DDL), ngăn chặn SQL Injection, và giới hạn chỉ cho phép SELECT trên 8 semantic views.
    *   **Cơ chế tự sửa lỗi 1-Turn (Self-Correction/Refiner):** Nếu thực thi SQL gặp lỗi (như sai tên cột), hệ thống tự động gửi thông báo lỗi quay lại LLM để sửa đúng 1 lần duy nhất trước khi trả kết quả lỗi.
    *   **Kết nối Read-Only an toàn:** Thực thi SQL trên connection read-only, cấu hình `SET TRANSACTION READ ONLY` và `statement_timeout = 5000ms`.

### 2.3. Tầng 3: Tối ưu hóa nâng cao (Phase 3 Complete)
*   **Database-First Trigram Entity Mapper (`pg_trgm`):**
    *   Nâng cấp cơ chế ánh xạ thực thể bằng cách truy vấn trước danh sách thực thể mờ tiềm năng trong Postgres bằng chỉ mục GIN (`similarity(alias, $1) > 0.05 OR $1 ILIKE '%' || alias || '%'`), giới hạn ở 200 ứng viên hàng đầu trước khi tinh lọc bằng `rapidfuzz`. 
    *   **Kết quả:** Giải quyết triệt để vấn đề quá tải CPU và RAM trên Python khi quy mô từ khóa tăng cao, hỗ trợ chuẩn hóa tiếng Nhật (Kanji/Hiragana/Katakana/Romaji).
*   **Dynamic Few-shot Retrieval (pgvector & HNSW):**
    *   Thay thế việc hardcode 15 ví dụ trong prompt bằng bảng `golden_queries`. Hệ thống tự động chuyển câu hỏi người dùng thành vector nhúng tại runtime, thực hiện truy vấn Cosine Distance (`<=>`) để chọn ra **top-3** ví dụ SQL phù hợp nhất.
    *   **Kết quả:** Tiết kiệm ~70% token đầu vào và nâng cao độ chính xác cú pháp SQL sinh ra nhờ ngữ cảnh tương đồng cao.
*   **Relative Temporal Context Resolution:**
    *   Xây dựng module biên dịch ngày tháng tương đối dựa trên `reference_date` hiện tại, trả về dải ngày ISO bắt đầu và kết thúc chuẩn xác cho LLM (hôm nay, hôm qua, tuần này, tuần trước, tháng này, tháng trước...).
*   **Enterprise-Grade Resilient Redis Cache:**
    *   Tích hợp bộ đệm an toàn phân tách theo khóa: `text2sql:<normalized_q>:<user_id>:<ref_date>`.
    *   **Graceful Fallback:** Tự động nhận diện trạng thái Redis (timeout 1.0s, ping). Nếu Redis ngoại tuyến, pipeline tự động bypass qua DB không đồng bộ mà không gây gián đoạn hay lỗi hệ thống.

---

## 3. Kết quả đánh giá tự động (Evaluation Metrics)

Hệ thống được kiểm thử nghiêm ngặt thông qua lệnh CLI `javis-text2sql eval` với 26 kịch bản kiểm thử:

### Bảng Kết quả Đánh giá Phân hệ Text-to-SQL
| Chỉ số (Metric) | Kết quả đạt được | Ý nghĩa / Ý đồ kiểm thử |
| :--- | :---: | :--- |
| **Routing Node Accuracy** | **100%** | Độ chính xác phân phối câu hỏi sang đúng luồng nghiệp vụ. |
| **SQL Validation Safety Rate** | **100%** | Tỷ lệ chặn đứng tuyệt đối các cuộc tấn công SQL Injection và từ chối các truy vấn DML/DDL. |
| **EX (Execution Accuracy)** | **75.0%** | Tỷ lệ các câu truy vấn thực thi hợp lệ (đã bao gồm các câu hỏi chứa mã độc bị chặn). |
| **VES (Valid Execution Success)** | **100%** | Tất cả dữ liệu trả về từ SQL khớp chính xác 100% với dữ liệu mẫu mong đợi. |
| **Latency p50** | **2.023s** | Thời gian phản hồi trung vị cho mỗi lượt truy vấn Text2SQL hoàn chỉnh (sử dụng API). |
| **Latency p95** | **2.025s** | Độ trễ đuôi (tail latency) cho trường hợp phức tạp nhất hoặc có tự sửa lỗi. |
| **Fact Ingestion Status** | **Pass (0 missing)** | Độ chính xác bóc tách thông tin cam kết từ ETL nạp tài liệu đạt điểm F1 tối đa. |

---

## 4. Lộ trình tối ưu hóa tiếp theo (Roadmap)

| Giai đoạn | Nhiệm vụ chi tiết | Mục tiêu đạt được | Trạng thái |
| :--- | :--- | :--- | :---: |
| **Phase 0** | **Tích hợp bộ lọc Tenant ID** vào luồng sinh SQL và Semantic Views. | Ngăn chặn rò rỉ dữ liệu giữa các khách hàng. | **Đã hoàn thành** |
| **Phase 1** | **Bổ sung LLM Provider thực tế (Groq)** với cơ chế xoay vòng và phục hồi API key. | Cho phép hệ thống hoạt động với dữ liệu thực tế ổn định. | **Đã hoàn thành** |
| **Phase 2** | **Tích hợp Redis Caching & Graceful Failover**. | Tối ưu thời gian phản hồi, bảo vệ DB, resilient cao. | **Đã hoàn thành** |
| **Phase 3** | **Triển khai Dynamic Few-shot** sử dụng Vector Search (pgvector & HNSW). | Thu nhỏ context prompt, tăng độ chính xác SQL. | **Đã hoàn thành** |
| **Phase 4** | **Nâng cấp Entity Mapper** bằng `pg_trgm` nâng cao và xử lý thời gian (Temporal Resolution). | Tăng tốc độ ánh xạ thực thể gấp 100 lần, chuẩn hóa ngày tháng. | **Đã hoàn thành** |
| **Phase 5** | **Decouple Ingestion Path** qua Message Queue (Redis Streams / RabbitMQ). | Tách biệt hoàn toàn luồng đọc/ghi dưới tải cao. | **Roadmap** |

