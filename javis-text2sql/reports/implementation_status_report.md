# Báo cáo Tiến trình Triển khai và Đánh giá Phân hệ Javis Text-to-SQL

Báo cáo này tổng hợp chi tiết những tính năng đã triển khai, các thành phần đã hoàn thành, cùng những thiếu sót, hạn chế hiện tại và lộ trình tối ưu hóa tiếp theo cho phân hệ **Text-to-SQL** thuộc dự án Trợ lý ảo Javis.

---

## 1. Tổng quan Phân hệ Javis Text-to-SQL
Trong kiến trúc tổng thể của Trợ lý ảo Javis, **Text-to-SQL** hoạt động như một công cụ chuyên trách (Tool) được gọi bởi **Routing Node** để xử lý các câu hỏi định lượng, thống kê, đếm hoặc lọc thông tin có cấu trúc. Phân hệ này truy vấn trên cơ sở dữ liệu quan hệ PostgreSQL được đồng bộ hóa từ các cuộc họp và tài liệu doanh nghiệp.

Kiến trúc thực tế hiện tại đã hiện thực hóa **Tầng 1 (Core Infrastructure)** và **Tầng 2 (Routing Node + Text2SQL cơ bản)** theo thiết kế của dự án.

---

## 2. Những gì đã triển khai được (Implemented Features)

### 2.1. Tầng 1: Core Infrastructure (Cơ sở hạ tầng cốt lõi)
*   **PostgreSQL Schema & Semantic Views:**
    *   Thiết lập lược đồ vật lý hoàn chỉnh gồm các bảng: `meetings`, `passages`, `turns`, `entity_aliases` và `commitments`.
    *   Xây dựng **8 Semantic Views** phẳng hóa cấu trúc dữ liệu JSONB phức tạp giúp LLM dễ dàng truy xuất:
        *   `v_topics`, `v_commitments`, `v_amounts`, `v_action_items`, `v_open_questions`, `v_statements`, `v_dates`, `v_speaker_turns`.
*   **ETL Ingestion Pipeline (Đường ống nạp dữ liệu):**
    *   **Rule-based Chunker:** Phân tách lượt thoại từ file markdown/hội thoại thô và tự động gộp nhóm (8-10 turns hoặc ngắt sớm nếu có khoảng lặng > 3 phút dựa trên timestamp).
    *   **LLM Metadata Enrichment:** Sử dụng LLM với cấu trúc đầu ra nghiêm ngặt qua **Pydantic (PassageEnrichmentSchema)** để tự động trích xuất: Topics, Entities, Keywords, Amounts, Dates, Commitments.
    *   **Data Loader bất đồng bộ:** Nạp dữ liệu song song sử dụng `asyncio` và kiểm soát tốc độ qua `Semaphore(10)`, cam kết ghi DB trong transaction an toàn, hỗ trợ ghi nhận trạng thái lỗi `enrichment_status = 'llm_failed'` nếu LLM gặp sự cố.
*   **Entity Aliases Seeding:**
    *   Bảng `entity_aliases` hỗ trợ chuẩn hóa thực thể đa ngôn ngữ (tiếng Việt và tiếng Nhật) kèm chỉ mục `pg_trgm` để tìm kiếm mờ (Fuzzy Search).

### 2.2. Tầng 2: Routing Node & Text2SQL Pipeline
*   **Routing Node (Bộ định tuyến câu hỏi):**
    *   Phân tích ý định câu hỏi để điều phối sang luồng `sql`, `rag`, hoặc `hybrid` dựa trên cơ chế **Keyword-based Heuristic** tối ưu cho cả tiếng Việt và tiếng Nhật. Luồng này xử lý logic Python local hoàn toàn, không phụ thuộc LLM bên ngoài giúp tối ưu latency.
*   **Text2SQL Pipeline (Đường ống NL-to-SQL):**
    *   **SQL Validation (AST Analysis):** Tích hợp thư viện `sqlglot` để phân tích cây cú pháp. Chặn các câu lệnh sửa đổi dữ liệu (DML/DDL), ngăn chặn SQL Injection, và giới hạn chỉ cho phép SELECT trên 8 semantic views.
    *   **Cơ chế tự sửa lỗi 1-Turn (Self-Correction/Refiner):** Nếu thực thi SQL gặp lỗi (như sai tên cột), hệ thống tự động gửi thông báo lỗi quay lại LLM để sửa đúng 1 lần duy nhất trước khi trả kết quả lỗi.
    *   **Kết nối Read-Only an toàn:** Thực thi SQL trên connection read-only, cấu hình `SET TRANSACTION READ ONLY` và `statement_timeout = 5000ms`.
    *   **System Prompt & Few-shot:** Tập prompt hệ thống truyền ngày tham chiếu hiện tại và đính kèm 15 ví dụ few-shot đa ngôn ngữ (hardcoded trong `prompt.py`).

### 2.3. Bộ đánh giá tự động (Evaluation Runner)
*   Được tích hợp trực tiếp qua CLI `javis-text2sql eval`.
*   **Cơ chế chạy test (Deterministic Sanity Check):** 
    *   Do lớp `Settings` và `CLI` hiện tại chưa hỗ trợ tham số `API_KEY` (OpenAI/Gemini), bộ Runner hiện đang sử dụng **Deterministic Mock Fixtures** (`FixtureLLMClient`).
    *   *Mục đích*: Đảm bảo logic xử lý dữ liệu, định tuyến và sinh SQL hoạt động đúng theo kịch bản mẫu trước khi kết nối API thực tế.
    *   *Kết quả hiện tại*: Recall trích xuất = 1.0, độ chính xác định tuyến = 100%, chặn 100% SQL Injection.
    *   *Độ trễ (Latency)*: Latency pipeline trung bình ghi nhận **~0.4 ms** là do sử dụng mock local, phản ánh hiệu năng tối ưu của logic Python core.

---

## 3. Những gì còn thiếu sót và hạn chế (Gaps & Weaknesses)

### 3.1. Chưa có tích hợp LLM Provider thực tế
*   **Hạn chế:** Code hiện tại mới chỉ định nghĩa `LLMClient` Protocol và bản Mock. Cả lớp `Settings` và `CLI` đều chưa có chỗ để cấu hình API Key hay chọn Provider (OpenAI/Google).

### 3.2. Thiếu cơ chế cô lập dữ liệu Multi-Tenant tại tầng SQL
*   **Rủi ro rò rỉ dữ liệu:** Cả Schema DB vật lý và các Semantic Views phẳng **hoàn toàn thiếu cột `tenant_id`**. LLM có thể sinh SQL quét toàn bộ bảng và trả về dữ liệu của tất cả khách hàng.

### 3.3. Chưa tích hợp Redis Caching
*   **Hạn chế:** Code hiện tại chưa có tích hợp Redis để cache kết quả SQL hoặc RAG.

### 3.4. Few-shot Examples bị hardcode cố định trong Prompt
*   **Hạn chế:** 15 ví dụ few-shot đang được lưu trữ tĩnh trong code, chiếm context token cố định và không tự động cập nhật theo ngữ cảnh câu hỏi.

### 3.5. Bộ xử lý thực thể (Entity Mapping) còn đơn giản
*   **Hạn chế:** `map_entities` chỉ dùng `ILIKE` đơn giản. Chưa có logic phân tích thời gian chuyên sâu ở backend Python (phụ thuộc hoàn toàn vào khả năng xử lý ngày tháng của LLM).

---

## 4. Lộ trình tối ưu hóa tiếp theo (Roadmap)

| Giai đoạn | Nhiệm vụ chi tiết | Mục tiêu đạt được | Độ ưu tiên |
| :--- | :--- | :--- | :---: |
| **Phase 0** | **Tích hợp bộ lọc Tenant ID** vào luồng sinh SQL và Semantic Views. | Ngăn chặn rò rỉ dữ liệu giữa các khách hàng. | **Khẩn cấp** |
| **Phase 1** | **Bổ sung LLM Provider thực tế** (OpenAI/Gemini/Anthropic) vào cấu trúc `Settings` và `CLI`. | Cho phép hệ thống hoạt động với dữ liệu thực. | **Cao** |
| **Phase 2** | **Tích hợp Redis Caching**. | Tối ưu thời gian phản hồi, giảm tải DB. | **Cao** |
| **Phase 3** | **Triển khai Dynamic Few-shot** sử dụng Vector Search (pgvector). | Thu nhỏ context prompt, tăng độ chính xác SQL. | **Trung bình** |
| **Phase 4** | **Nâng cấp Entity Mapper** bằng `pg_trgm` nâng cao và xử lý thời gian (Temporal Resolution). | Tăng khả năng map thực thể và chuẩn hóa ngày tháng. | **Trung bình** |
| **Phase 5** | **Decouple Ingestion Path** qua Redis Streams/MQ. | Đảm bảo tính sẵn sàng của luồng đọc khi có tải ghi lớn. | **Thấp** |
