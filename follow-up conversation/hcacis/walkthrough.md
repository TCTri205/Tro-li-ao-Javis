# HCACIS: Hướng dẫn Triển khai Toàn diện từ A-Z

Hệ thống **Multi-Engine Router (SQL, RAG, Web, Pure LLM)** đã được triển khai hoàn chỉnh tại thư mục `d:\javis_text2sql\hcacis`. Dưới đây là hướng dẫn từng bước cụ thể để một người dùng mới có thể chạy pipeline từ trạng thái hoàn toàn trống rỗng.

## Bước 1: Khởi động Database và nạp dữ liệu (Numeric SQL)

Hệ thống phụ thuộc vào PostgreSQL Database của `numeric_sql_tool_v2` để chạy SQL Engine và trích xuất dữ liệu làm RAG Vector.

1. Bật terminal và truy cập thư mục gốc:
   ```bash
   cd d:\javis_text2sql\numeric_sql_tool_v2
   ```
2. Khởi chạy Docker container cho PostgreSQL:
   ```bash
   docker compose up -d
   ```
3. Nạp (Restore) toàn bộ dữ liệu 9 scripts hội thoại vào CSDL (yêu cầu máy có cài Python):
   ```bash
   python scripts/restore_db.py
   ```
   *Quá trình này sẽ tạo các bảng `transcripts`, `chunks_turn`... và insert dữ liệu.*

## Bước 2: Thiết lập Biến Môi trường (.env)

Hệ thống HCACIS chia sẻ chung cấu hình môi trường với `numeric_sql_tool_v2`. Hãy kiểm tra file `.env` tại `d:\javis_text2sql\numeric_sql_tool_v2\.env` (nếu chưa có, copy từ `.env.example`).

Mở file `.env` và đảm bảo các dòng sau chính xác:
```env
# Connection tới PostgreSQL trong Docker
NUMERIC_SQL_DATABASE_URL=postgresql://app_user:app_password@localhost:54331/app_db

# Thêm khóa API của Google (Gemini) để gọi LLM và Embeddings
GOOGLE_API_KEY=AIzaSy...your_gemini_key_here...
```

## Bước 3: Cài đặt Thư viện cho HCACIS

HCACIS yêu cầu thêm một số thư viện mạnh mẽ như LangGraph, ChromaDB, và DuckDuckGo.

1. Mở terminal mới và chuyển sang thư mục hệ thống:
   ```bash
   cd d:\javis_text2sql\hcacis
   ```
2. Cài đặt các thư viện từ file requirements:
   ```bash
   pip install -r requirements.txt
   ```

## Bước 4: Xây dựng Vector Database (RAG Data Builder)

Sau khi Database Postgres đã có dữ liệu, ta cần trích xuất Text ra ChromaDB để hỗ trợ RAG (đọc chi tiết văn bản).

1. Đảm bảo bạn vẫn đang ở thư mục `hcacis`.
2. Chạy lệnh sau để chuyển đổi dữ liệu từ SQL sang Vector:
   ```bash
   python build_rag_data.py
   ```
   > [!NOTE]
   > Script sẽ tự động connect vào Postgres, quét qua cả 9 scripts hội thoại, tạo chunk và dùng mô hình nhúng (Google Embeddings) để lưu vào thư mục `d:\javis_text2sql\hcacis\chroma_db`. 
   > Bạn sẽ thấy thông báo: `Indexed final ... documents. Done building RAG data!`

## Bước 5: Chạy Kịch bản Hội thoại Ngẫu nhiên (Multi-Engine Pipeline)

Sau khi Vector DB đã sẵn sàng, bạn có thể chạy file [main.py](file:///d:/javis_text2sql/hcacis/main.py) để xem cách hệ thống định tuyến (Route) câu hỏi.

Chạy lệnh:
```bash
python main.py
```

### Cách Hệ thống Hoạt động trong `main.py`:
File test mô phỏng 5 lượt trò chuyện (Turns) ngẫu nhiên:
1. **Turn 1 (Web)**: Hỏi thông tin một công ty Nhật. `Detector` nhận diện `intent_category=web` -> Gọi DuckDuckGo.
2. **Turn 2 (Pure LLM)**: "Tóm tắt lại đi". `Detector` nhận diện `pure_llm` -> Không query gì, tự dùng lịch sử chat tóm tắt.
3. **Turn 3 (SQL)**: "Cuộc họp dài nhất?". `Detector` nhận diện `sql` -> Gọi pipeline SQL tìm MAX duration -> Lưu lại `transcript_id` vào Memory.
4. **Turn 4 (RAG)**: "Trong cuộc gọi ĐÓ nội dung là gì?". `Detector` nhận diện follow-up + `rag` -> Chuyển hướng sang ChromaDB, đính kèm cái `transcript_id` từ Turn 3 vào Filter.
5. **Turn 5 (SQL)**: "Nhắc đến Umeda mấy lần?". `Detector` quay lại `sql` để đếm `COUNT(text)`.

> [!TIP]
> Bạn có thể mở file `main.py` và sửa list `queries` thành bất kỳ câu hỏi nào bạn muốn test để thấy được sự linh hoạt của hệ thống!
