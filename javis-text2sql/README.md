# Module Javis Text-to-SQL

Phân hệ xử lý câu hỏi định lượng và số liệu dựa trên cơ sở dữ liệu quan hệ PostgreSQL được đồng bộ hóa từ hội thoại cuộc họp của Trợ lý ảo Javis. Module này hiện thực hóa **Tầng 1 (Core Infrastructure)** và **Tầng 2 (Routing Node + Text2SQL cơ bản)** theo thiết kế tại [text2sql_proposal.md](docs/text2sql_proposal.md).

---

## 🚀 Tính năng đã triển khai

### Tầng 1: Core Infrastructure
* **PostgreSQL Schema & Views:** Hệ thống bảng vật lý (`meetings`, `passages`, `turns`, `entity_aliases`, `commitments`) và 8 semantic views phẳng hóa dữ liệu JSONB giúp LLM truy vấn an toàn và hiệu quả.
* **Entity Aliases Seeding:** Hỗ trợ chuẩn hóa thực thể đa ngôn ngữ (tiếng Việt và tiếng Nhật) thông qua bảng `entity_aliases` từ dữ liệu mẫu.
* **ETL Pipeline:** 
  * **Rule-based Chunker:** Phân tách turns nói và gộp passage thông minh (8-10 turns hoặc ngắt khi có khoảng lặng > 3 phút).
  * **LLM Metadata Enrichment:** Trích xuất tự động các thông tin có cấu trúc (chủ đề, thực thể, ngân sách, mốc thời gian, cam kết) sử dụng Pydantic Structured Output.
  * **Loader:** Nạp dữ liệu song song (asyncio + semaphore) trong transaction an toàn, hỗ trợ cơ chế fallback tự động ghi nhận trạng thái lỗi.

### Tầng 2: Routing Node & Text2SQL Pipeline
* **Routing Node:** Phân tích câu hỏi tự nhiên để điều phối sang luồng `sql`, `rag`, hoặc `hybrid` dựa trên regex heuristic tối ưu cho cả tiếng Việt và tiếng Nhật.
* **Text2SQL Pipeline:** Dịch câu hỏi thành câu lệnh SQL và thực thi trên kết nối Read-only.
* **SQL Validation:** Tích hợp bộ parse AST bằng `sqlglot` để chặn các lệnh ghi dữ liệu (DML/DDL), ngăn chặn SQL Injection và giới hạn chỉ cho phép SELECT trên 8 semantic views được chỉ định.
* **1-Turn Refiner:** Tự động bắt lỗi cú pháp DB và gọi LLM sửa lại SQL đúng 1 lần duy nhất để tối ưu tỷ lệ chạy thành công.
* **System Prompt & 15 Few-shot Examples:** Tập hợp các câu hỏi mẫu thực tế đa ngôn ngữ giúp định hình câu lệnh SQL chuẩn xác.

---

## 🛠️ Thiết lập Môi trường

Yêu cầu: **Python >= 3.11** và **Docker** (để chạy PostgreSQL).

1. **Di chuyển vào thư mục module:**
   ```powershell
   cd d:\VJ\Tro-li-ao-Javis\javis-text2sql
   ```

2. **Cài đặt thư viện phát triển:**
   ```powershell
   python -m pip install -e .[dev]
   ```

3. **Khởi chạy PostgreSQL bằng Docker:**
   ```powershell
   docker compose up -d
   ```

4. **Cấu hình biến môi trường:**
   Thiết lập URL kết nối đến cơ sở dữ liệu PostgreSQL trong môi trường:
   ```powershell
   # Windows PowerShell
   $env:TEXT2SQL_DATABASE_URL="postgresql://javis_etl:javis_etl@localhost:54329/javis_text2sql"
   ```

---

## 💻 Sử dụng CLI

Module cung cấp CLI tool `javis-text2sql` để quản lý các tác vụ:

* **Tạo cấu trúc database (Migration):**
  ```powershell
  javis-text2sql migrate
  ```

* **Seed dữ liệu thực thể mẫu:**
  ```powershell
  javis-text2sql seed
  ```

* **Nạp tài liệu mẫu (Ingest samples):**
  Nạp 3 tài liệu hội thoại kiểm thử bằng mock LLM:
  ```powershell
  javis-text2sql ingest-samples --fixture-llm
  ```

* **Kiểm tra tính toàn vẹn của dữ liệu và views:**
  ```powershell
  javis-text2sql verify
  ```

* **Chạy đánh giá tự động (Evaluation Run):**
  Chạy bộ đánh giá logic trên fixture dữ liệu mẫu để xuất báo cáo:
  ```powershell
  javis-text2sql eval --output eval_report.json
  ```

---

## 🧪 Chạy Kiểm thử (Testing)

* **Chạy toàn bộ Unit Tests:**
  ```powershell
  python -m pytest
  ```
  *(Unit tests sử dụng mock LLM client và mock DB connection, không yêu cầu database thật).*

* **Chạy Integration Tests (Yêu cầu DB thật):**
  Thiết lập URL database test trong môi trường:
  ```powershell
  $env:TEXT2SQL_TEST_DATABASE_URL="postgresql://javis_etl:javis_etl@localhost:54329/javis_text2sql_test"
  python -m pytest -m integration
  ```

