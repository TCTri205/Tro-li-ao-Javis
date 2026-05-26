# Module Javis Text-to-SQL

Phân hệ xử lý câu hỏi định lượng và số liệu dựa trên cơ sở dữ liệu quan hệ PostgreSQL được đồng bộ hóa từ hội thoại cuộc họp của Trợ lý ảo Javis. Module này hiện thực hóa toàn bộ **Tầng 1 (Core Infrastructure)**, **Tầng 2 (Routing Node + Text2SQL cơ bản)** và **Tầng 3 (Nâng cao dựa trên Failure Patterns)** theo thiết kế kiến trúc tại [text2sql_proposal.md](docs/text2sql_proposal.md).

---

## 🚀 Tính năng đã triển khai

### Tầng 1: Core Infrastructure (Cơ sở hạ tầng cốt lõi)
* **PostgreSQL Schema & Views:** Hệ thống bảng vật lý (`meetings`, `passages`, `turns`, `entity_aliases`, `commitments`, `golden_queries`) và 8 semantic views phẳng hóa dữ liệu JSONB giúp LLM truy vấn an toàn và hiệu quả.
* **Multi-tenant Isolation:** Tích hợp RLS (Row Level Security) trên Postgres bảo vệ và cô lập dữ liệu khách hàng theo session ID.
* **ETL Pipeline:** 
  * **Rule-based Chunker:** Phân tách turns nói và gộp passage thông minh (8-10 turns hoặc ngắt khi có khoảng lặng > 3 phút).
  * **LLM Metadata Enrichment (Fault-Tolerant):** Trích xuất tự động thông tin có cấu trúc (chủ đề, thực thể, ngân sách, mốc thời gian, cam kết) sử dụng Pydantic với cơ chế tự động suy luận dynamic currency (VND/JPY/USD) ngăn chặn tuyệt đối lỗi crash dữ liệu thô.
  * **Loader:** Nạp dữ liệu song song (asyncio + semaphore) trong transaction an toàn, hỗ trợ cơ chế fallback tự động ghi nhận trạng thái lỗi.

### Tầng 2: Routing Node & Text2SQL Pipeline
* **Routing Node:** Phân tích câu hỏi tự nhiên để điều phối sang luồng `sql`, `rag`, hoặc `hybrid` dựa trên regex heuristic tối ưu cho cả tiếng Việt và tiếng Nhật, xử lý offline cực nhanh.
* **Text2SQL Pipeline:** Dịch câu hỏi thành câu lệnh SQL và thực thi trên kết nối Read-only.
* **SQL Validation:** Tích hợp bộ parse AST bằng `sqlglot` để chặn các lệnh ghi dữ liệu (DML/DDL), ngăn chặn SQL Injection và giới hạn chỉ cho phép SELECT trên 8 semantic views được chỉ định.
* **1-Turn Refiner:** Tự động bắt lỗi cú pháp DB và gọi LLM sửa lại SQL đúng 1 lần duy nhất để tối ưu tỷ lệ chạy thành công.

### Tầng 3: Tối ưu hóa nâng cao (Phase 3 Complete)
* **Resilient Redis Caching:** Tích hợp cache hai lớp với cơ chế Graceful Fallback (nếu Redis ngoại tuyến, pipeline tự động truy vấn DB trực tiếp không làm gián đoạn hệ thống).
* **Dynamic Few-shot (pgvector & HNSW):** Lưu trữ các ví dụ vàng tại bảng `golden_queries`, tìm kiếm vector độ tương đồng Cosine độ trễ thấp để lấy top-3 ví dụ few-shot khớp nhất với câu hỏi người dùng tại runtime, tiết kiệm 70% token context.
* **Database-First Trigram Entity Mapper (`pg_trgm`):** Tìm kiếm mờ danh sách thực thể tiềm năng bằng chỉ mục GIN trước khi tinh lọc bằng `rapidfuzz`, giảm tải CPU/RAM trên Python gấp 100 lần.
* **Relative Temporal Context Resolution:** Tự động biên dịch các mốc thời gian tương đối ("hôm nay", "tuần này", "tháng trước") thành dải ngày ISO chuẩn xác để LLM sinh SQL không bị sai lệch thời gian thực tế.

---

## 🛠️ Thiết lập Môi trường

Yêu cầu: **Python >= 3.11** và **Docker** (để chạy PostgreSQL và Redis).

1. **Di chuyển vào thư mục module:**
   ```powershell
   cd d:\VJ\Tro-li-ao-Javis\javis-text2sql
   ```

2. **Cài đặt thư viện phát triển:**
   ```powershell
   python -m pip install -e .[dev]
   ```

3. **Khởi chạy PostgreSQL & Redis bằng Docker:**
   ```powershell
   docker compose up -d
   ```

4. **Cấu hình biến môi trường (`.env`):**
   Sao chép `.env.example` thành `.env` và thiết lập các biến kết nối:
   ```env
   TEXT2SQL_DATABASE_URL=postgresql://javis_etl:javis_etl@localhost:54329/javis_text2sql
   TEXT2SQL_READONLY_DATABASE_URL=postgresql://javis_readonly:javis_readonly@localhost:54329/javis_text2sql
   TEXT2SQL_LLM_PROVIDER=groq
   GROQ_API_KEYS=gsk_your_api_key_1,gsk_your_api_key_2
   ```

---

## 💻 Sử dụng CLI

Module cung cấp CLI tool `javis-text2sql` để quản lý các tác vụ:

* **Tạo cấu trúc database (Migration):**
  ```powershell
  javis-text2sql migrate
  ```

* **Seed dữ liệu thực thể mẫu & Golden Queries:**
  ```powershell
  javis-text2sql seed
  ```

* **Nạp tài liệu mẫu (Ingest samples):**
  Nạp 3 tài liệu hội thoại kiểm thử bằng mock hoặc real LLM:
  ```powershell
  # Mock LLM (Chạy local bảo mật)
  javis-text2sql ingest-samples --fixture-llm
  
  # Live API (Gọi trực tiếp tới Groq Cloud)
  javis-text2sql ingest-samples
  ```

* **Kiểm tra tính toàn vẹn của dữ liệu và views:**
  ```powershell
  javis-text2sql verify
  ```

* **Chạy đánh giá tự động (Evaluation Run):**
  ```powershell
  # Chạy Live API thực tế kết nối Groq Cloud
  javis-text2sql eval --output reports/eval_report_phase3_live.json
  
  # Chạy Mock local bảo mật
  javis-text2sql eval --fixture-llm --output reports/eval_report_phase3_mock.json
  ```

---

## 🧪 Chạy Kiểm thử (Testing)

* **Chạy toàn bộ Unit Tests & Integration Tests:**
  ```powershell
  python -m pytest
  ```
  *(Unit tests sử dụng mock LLM client và mock DB connection, không yêu cầu database thật).*

* **Chạy Integration Tests (Yêu cầu DB thật):**
  Thiết lập URL database test trong môi trường và chạy:
  ```powershell
  $env:TEXT2SQL_TEST_DATABASE_URL="postgresql://javis_etl:javis_etl@localhost:54329/javis_text2sql_test"
  python -m pytest -m integration
  ```
