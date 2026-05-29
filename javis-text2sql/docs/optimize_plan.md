# Kế hoạch Tối ưu hóa Phân hệ Javis Text-to-SQL (Consolidated Optimize Plan)

Tài liệu này tổng hợp toàn bộ các điểm chưa tối ưu, các lỗi tiềm ẩn được phát hiện sau khi đánh giá 100 test cases thực tế, và đề xuất giải pháp kỹ thuật chi thể để nâng cấp hệ thống toàn diện trong một lần duy nhất.

---

## 1. Tầng Mô hình & Ngữ nghĩa (LLM Semantic & Hallucination)

### 🔴 Vấn đề hiện tại
* **Hallucination về Schema (Lỗi Case 097)**: LLM tự ý sinh ra cột `s.entity` trong `v_statements` thay vì sử dụng đúng view `v_topics` với điều kiện `source_type = 'entity'`.
* **Sự nhầm lẫn giữa các View**: LLM đôi khi nhầm lẫn giữa `v_action_items` (các công việc cần làm được ghi nhận trong cuộc họp) và `v_commitments` (cam kết cụ thể có người chịu trách nhiệm và deadline rõ ràng).

### 💡 Giải pháp đề xuất
1. **Cập nhật Prompt System (`src/javis_text2sql/query/pipeline.py`)**:
   Bổ sung phần ràng buộc nghiêm ngặt (Strict Schema Guards) vào Prompt để định hình rõ cấu trúc của từng view.
   ```markdown
   CRITICAL SCHEMA RULES:
   - DO NOT reference 'entity' column in 'v_statements'. 'v_statements' has NO entity columns.
   - To query named entities (e.g., VJ Technologies, AJ Technologies), you MUST query 'v_topics' where 'source_type = 'entity'' and filter on the 'topic' column.
   - Distinct meeting titles should be queried from 'v_topics' or 'v_speaker_turns', never join 'v_topics' with 'v_statements' unnecessarily.
   ```
2. **Cập nhật Few-shot Golden Queries (`migrations/002_golden_queries.sql`)**:
   Thêm ít nhất 2 ví dụ mẫu rõ ràng về việc trích xuất thực thể từ view `v_topics` để mô hình học theo cơ chế Dynamic Few-Shot.
   ```sql
   -- Ví dụ bổ sung:
   -- Q: "VJ Technologies に言及している会議タイトルを一覧表示してください。"
   -- SQL: SELECT DISTINCT meeting_title FROM v_topics WHERE topic ILIKE '%VJ Technologies%' AND source_type = 'entity';
   ```

---

## 2. Tầng Tìm kiếm Vector (Embedding & Vector Retrieval)

### 🔴 Vấn đề hiện tại
* **Fallback về Mock Embedding (MD5 Hash)**: Do không có `OPENAI_API_KEY` hợp lệ, hệ thống đang dùng thuật toán MD5 để sinh vector giả lập. 
* **Hạn chế**: Vector giả lập MD5 chỉ hoạt động khi từ khóa trong câu hỏi của người dùng khớp *chính xác tuyệt đối* với câu hỏi mẫu (chỉ khớp chuỗi). Nếu người dùng dùng từ đồng nghĩa (ví dụ: dùng `"タスク"` thay cho `"コミットメント"`), pgvector sẽ không thể tìm thấy ví dụ Few-Shot tương đồng phù hợp nhất.

### 💡 Giải pháp đề xuất
1. **Tích hợp Open-source Embedding Local (Sử dụng `transformers.js` hoặc `sentence-transformers`)**:
   - Viết thêm một tùy chọn `TEXT2SQL_EMBEDDING_PROVIDER=local` trong file cấu hình.
   - Sử dụng một mô hình cực nhẹ như `all-MiniLM-L6-v2` hoặc `paraphrase-multilingual-MiniLM-L12-v2` (hỗ trợ đa ngôn ngữ Nhật - Việt - Anh tốt) chạy trực tiếp thông qua thư viện `sentence-transformers` trên Python.
   - Không phụ thuộc vào API Key bên ngoài và chi phí truy vấn bằng 0.

---

## 3. Tầng Bảo mật & Kiểm duyệt (Security Validation & AST Guards)

### 🔴 Vấn đề hiện tại
* **Chặn theo bộ lọc từ khóa (Blacklist keywords)**: Hiện tại, cơ chế chặn an toàn đang kiểm tra thủ công các từ khóa nhạy cảm như `DROP`, `DELETE` bằng chuỗi ký tự thường. 
* **Lỗ hổng tiềm ẩn**: Nếu người dùng viết SQL lồng nhau phức tạp hoặc sử dụng các hàm hệ thống của Postgres (ví dụ: `pg_sleep()`, `current_setting()`), các từ khóa blacklist thô sơ có thể bị bỏ lọt.

### 💡 Giải pháp đề xuất
1. **Chuyển hẳn sang kiểm duyệt dựa trên AST (Abstract Syntax Tree) bằng `sqlglot`**:
   - Hoàn toàn không dùng kiểm tra chuỗi (blacklist string check).
   - Duyệt qua cây AST của câu SQL được LLM sinh ra:
     - **Quy tắc 1**: Bắt buộc Node gốc phải là `sqlglot.expressions.Select`.
     - **Quy tắc 2**: Duyệt qua tất cả các Node `sqlglot.expressions.Table` (nguồn dữ liệu trong mệnh đề `FROM`, `JOIN`) và chỉ cho phép những bảng/view nằm trong danh sách trắng (`ALLOWED_VIEWS`).
     - **Quy tắc 3**: Chặn tất cả các hàm hệ thống Postgres ngoại trừ các hàm tính toán cơ bản như `SUM`, `COUNT`, `AVG`, `DATE`, `NOW`.

---

## 4. Tầng Hạ tầng & Caching (Infrastructure & Caching)

### 🔴 Vấn đề hiện tại
* **Redis Caching bị Offline**: Nhật ký hệ thống thông báo `Redis is not available, running without cache`.
* **Hạn chế**: Mỗi câu hỏi trùng lặp hoặc tương tự của người dùng đều phải gửi lên Groq Cloud, gây tốn token và tăng độ trễ (latency) không đáng có.

### 💡 Giải pháp đề xuất
1. **Nâng cấp `docker-compose.yml`**:
   Thêm dịch vụ Redis vào docker-compose để kích hoạt tính năng cache tự động của phân hệ Text-to-SQL.
   ```yaml
   services:
     postgres:
       # Cấu hình Postgres hiện tại...
     
     redis:
       image: redis:7-alpine
       ports:
         - "6379:6379"
       restart: always
   ```
2. **Cập nhật `.env`**:
   ```env
   TEXT2SQL_REDIS_URL=redis://localhost:6379/0
   ```

---

## 5. Xử lý Logic thời gian tương đối (Temporal Date Resolution)

### 🔴 Vấn đề hiện tại
* **Mốc thời gian tĩnh (Static Reference Date)**: Hiện tại `reference_date` đang được truyền cứng là ngày `2026-05-26` hoặc lấy ngày giờ hệ thống hiện tại.
* **Hạn chế**: Khi người dùng hỏi các câu liên quan đến thời gian tương đối như *"Nhiệm vụ tuần này"*, *"Cam kết trong ngày hôm sau"*, LLM cần biết chính xác ngày diễn ra cuộc họp đó là ngày nào để cộng/trừ ngày cho đúng, chứ không thể dựa vào ngày chạy ứng dụng hiện tại.

### 💡 Giải pháp đề xuất
1. **Truy vấn ngày họp trước khi sinh SQL (Meeting Date Detection)**:
   - Khi người dùng hỏi câu có yếu tố thời gian tương đối (Bộ router nhận diện `requires_numeric` hoặc keyword thời gian).
   - Hệ thống sẽ tìm kiếm cuộc họp gần nhất hoặc cuộc họp được nhắc tới trong ngữ cảnh để lấy `meeting_date` thực tế trong bảng `meetings`.
   - Gắn `meeting_date` đó làm `reference_date` truyền vào prompt của LLM. Việc này giúp LLM dịch từ *"ngày mai"*, *"tuần sau"* ra đúng giá trị `DATE 'YYYY-MM-DD'` chính xác tuyệt đối.

---

## 📋 Danh sách các đầu việc cần chỉnh sửa một lần (Consolidated Action Items)

| ID | Module cần sửa | Công việc cụ thể | Trạng thái |
|---|---|---|---|
| **#01** | `migrations/002_golden_queries.sql` | Thêm ví dụ truy vấn Named Entities bằng `v_topics`. | 🟩 Chưa thực hiện |
| **#02** | `src/javis_text2sql/query/pipeline.py` | Cập nhật Strict Prompts cấm dùng `s.entity`, hướng dẫn dùng `v_topics`. | 🟩 Chưa thực hiện |
| **#03** | `src/javis_text2sql/query/pipeline.py` | Nâng cấp bộ validator bảo mật: Chuyển hoàn toàn sang kiểm tra AST bằng `sqlglot`. | 🟩 Chưa thực hiện |
| **#04** | `docker-compose.yml` | Bổ sung container `redis:7-alpine`. | 🟩 Chưa thực hiện |
| **#05** | `testcase-text2sql.csv` | Sửa lại SQL của Case 097 theo đúng chuẩn ngữ nghĩa. | 🟩 Chưa thực hiện |
| **#06** | `eval_testcases.py` | Cập nhật parser để đọc chính xác các câu SQL viết xuống dòng trong file CSV. | 🟩 Chưa thực hiện |
