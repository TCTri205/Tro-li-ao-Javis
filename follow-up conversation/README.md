# HCACIS - Hierarchical Context-Aware Conversational Intelligence System

HCACIS là hệ thống xử lý ngôn ngữ tự nhiên nhiều lớp (Multi-layered), kết hợp **Multi-Engine** (SQL, RAG, Web, Pure LLM) và **Multi-LLM** (Groq Llama-3.3-70B, Ollama Qwen-2.5-7B) để giải quyết triệt để bài toán **Follow-up Conversation** (trò chuyện tiếp nối) với ngữ cảnh phức tạp. Hệ thống sử dụng Neo4j Graph DB để phân giải đại từ và duy trì Context bền vững.

---

## 1. Cấu trúc thư mục (Hướng dẫn bàn giao code)

Khi nén file code để gửi, **CẦN NÉN 2 THƯ MỤC SAU ĐÂY** vào chung một file zip (để giữ nguyên cấu trúc tham chiếu chéo):

```text
d:\javis_text2sql\
├── hcacis/                      <-- (Thư mục chính) Toàn bộ kiến trúc 4 lớp
│   ├── scenarios/               <-- Các kịch bản test (.txt)
│   ├── .env                     <-- File cấu hình môi trường
│   ├── main.py                  <-- Entrypoint chạy ứng dụng
│   ├── layer1_detector.py
│   ├── layer2_memory.py
│   ├── layer3_planner.py
│   ├── layer4_generator.py
│   ├── context_graph.py
│   ├── cache_manager.py
│   └── ... (Các file .py khác)
│
└── numeric_sql_tool_v2/         <-- (Thư mục phụ thuộc) Engine xử lý SQL
    ├── src/numeric_sql_tool/    <-- Chứa pipeline.py, heuristics.py
    └── ...
```

> **LƯU Ý:** 
> - KHÔNG nén các thư mục: `.venv`, `__pycache__`, và `chroma_db` (vì chúng có dung lượng lớn và tự động sinh ra khi chạy).

---

## 2. Hướng dẫn Cài đặt Môi trường (Dành cho Windows)

Để chắc chắn 100% hệ thống chạy được trên một máy tính mới (đặc biệt là Windows), hãy làm lần lượt từng bước chi tiết sau:

### Bước 2.1: Khởi động PostgreSQL & Redis bằng Docker Compose
Trong thư mục `numeric_sql_tool_v2` đã có sẵn file cấu hình `docker-compose.yml`. Bạn chỉ cần:
1. Mở Terminal (CMD/PowerShell).
2. Chuyển hướng vào thư mục `numeric_sql_tool_v2`:
```bash
cd d:\javis_text2sql\numeric_sql_tool_v2
```
3. Chạy lệnh sau để khởi động cả PostgreSQL và Redis cùng lúc:
```bash
docker-compose up -d
```
*(Nếu bạn dùng Docker bản mới, lệnh có thể là `docker compose up -d`)*.

### Bước 2.2: Cài đặt Neo4j Desktop (Để chạy Trí nhớ Graph DB)
1. Tải **Neo4j Desktop** dành cho Windows tại: `https://neo4j.com/download/` (Cần tạo tài khoản miễn phí để tải).
2. Cài đặt và mở ứng dụng Neo4j Desktop.
3. Nhấn vào nút **New Project**, sau đó chọn **Add Local DBMS**.
4. Khai báo Mật khẩu là `123456789` *(Rất quan trọng, phải nhập đúng vì code đã hardcode pass này trong file .env)*.
5. Nhấn nút **Start** để bật Database. Khi thành công, nó sẽ hiển thị trạng thái đang chạy (Active) ở port `7687` và `7474`.
6. Tùy chọn: Bạn có thể nhấn vào nút **Open** để mở trình duyệt Neo4j Browser (Đăng nhập bằng user: `neo4j` / pass: `123456789`) để xem mô hình Graph 3D cực kỳ trực quan khi chat.

### Bước 2.3: Cài đặt Ollama (Để chạy Local LLM miễn phí)
1. Tải **Ollama** tại: `https://ollama.com/download/windows`
2. Cài đặt xong, mở Command Prompt và chạy lần lượt 2 lệnh sau để tải AI Model về máy:
```bash
ollama pull qwen2.5:7b          
# Đây là Model Qwen 7B (hỗ trợ tiếng Nhật cực tốt), dùng cho Layer 4 sinh câu trả lời.

ollama pull nomic-embed-text    
# Đây là Model chuyên dùng để nhúng Vector (Embeddings) lưu vào ChromaDB cho RAG Engine.
```
*(Lưu ý: Tổng dung lượng tải khoảng 5GB, hãy giữ mạng ổn định và chờ tải xong 100%).*

> **💡 MẸO DÀNH CHO MÁY YẾU:**
> Nếu máy của bạn (hoặc máy khách hàng) cấu hình quá yếu, không chạy nổi model Qwen 7B, bạn không cần phải tải nó. Bạn chỉ cần tải model siêu nhẹ `nomic-embed-text` (để nhúng vector). Sau đó, hãy đổi cấu hình trong file `.env` thành:
> ```env
> GENERATOR_PROVIDER=groq
> GENERATOR_MODEL=llama-3.3-70b-versatile
> ```
> Hệ thống sẽ tự động dùng sức mạnh API của Groq trên Cloud để sinh câu trả lời, giúp máy tính chạy mượt mà mà không lo bị tràn RAM.

---

## 3. Cấu hình Code & Nạp Dữ Liệu (Data Ingestion)

Để hệ thống có thể chạy được, bạn cần cài đặt môi trường và nạp đầy đủ dữ liệu cho cả 3 Engine: PostgreSQL (SQL), ChromaDB (RAG), và Neo4j (Graph).

### Bước 3.1: Khởi tạo môi trường Python
Yêu cầu máy tính đã cài đặt **Python 3.10+**. Mở Terminal (trong VSCode hoặc CMD), chuyển hướng vào thư mục code:
```bash
cd d:\javis_text2sql\hcacis
python -m venv .venv
.venv\Scripts\activate
pip install neo4j chromadb langchain_ollama redis psycopg2 pydantic groq duckduckgo-search asyncpg python-dotenv
```

### Bước 3.2: Cấu hình API Key (File .env)
Mở file `.env` trong thư mục `hcacis`, tìm dòng `GROQ_API_KEY` và điền API Key Groq của bạn vào:
```env
# Dùng cho Layer 1 (Detector) và Layer 3 (Numeric Pipeline)
GROQ_API_KEY="gsk_nhập_key_của_bạn_vào_đây"

# Database Connections (Cứ để nguyên nếu bạn đã làm đúng theo Bước 2)
NEO4J_URI="bolt://localhost:7687"
NEO4J_USER="neo4j"
NEO4J_PASSWORD="123456789"
REDIS_URL="redis://localhost:6379"
```

### Bước 3.3: Nạp dữ liệu vào PostgreSQL (Dành cho SQL Engine)
Hệ thống có sẵn file backup dữ liệu ở thư mục `numeric_sql_tool_v2`. Bạn hãy dùng lệnh `docker-compose` để nạp thẳng dữ liệu vào container:
```bash
cd d:\javis_text2sql\numeric_sql_tool_v2
docker-compose exec -T postgres psql -U app_user -d app_db < dump-app_db-202606041640.sql
```
*(Lưu ý: Bắt buộc phải có chữ `-T` để không bị lỗi pseudo-TTY khi redirect file trên Windows).*

### Bước 3.4: Nạp dữ liệu vào ChromaDB (Dành cho RAG Engine)
Sau khi PostgreSQL đã có dữ liệu, hãy chạy file code sau để bóc tách text từ Postgres, dùng Ollama mã hóa (embed) và lưu vào ChromaDB:
```bash
cd d:\javis_text2sql\hcacis
python build_rag_data.py
```
*(Lưu ý: Quá trình này sẽ mất một lúc để Ollama xử lý nhúng Vector).*

### Bước 3.5: Nạp dữ liệu vào Neo4j (Dành cho Graph Memory)
Cuối cùng, chạy script sau để xây dựng cấu trúc Đồ thị Tri thức (Nodes & Edges) ban đầu cho hệ thống nhận diện Context:
```bash
python build_graph_data.py
```

---

## 4. Chạy Hệ thống & Kiểm thử

Sau khi mọi thứ đã được bật (Docker chuyển xanh, Neo4j Desktop đang Start, Ollama nằm ở khay hệ thống) và cài đặt xong thư viện, bạn đã sẵn sàng!

Để kiểm tra độ "bá đạo" của khả năng nhớ ngữ cảnh xuyên suốt (Khắc phục hoàn toàn lỗi Follow-up), hãy chạy lệnh:
```bash
cd d:\javis_text2sql\hcacis
python main.py -s scenarios\scenario_context_shift_test.txt
```

**Các tùy chọn kịch bản khác:**
* Chạy kịch bản tổng hợp dài (hơn 10 turns): `python main.py -s scenarios\scenario_complete.txt`
* Chạy kịch bản cơ bản mặc định: `python main.py`

---

## 5. Xử lý sự cố thường gặp (Troubleshooting)

1. **Lỗi `Failed to connect to Neo4j. Falling back to in-memory mode`**:
   - Bạn quên bấm nút "Start" trong Neo4j Desktop, hoặc lúc tạo nhập sai pass `123456789`. Bạn có thể chạy tạm bằng in-memory, nhưng Graph sẽ bị reset khi tắt terminal.
2. **Lỗi `ModuleNotFoundError: No module named 'numeric_sql_tool_v2'`**:
   - Thư mục `hcacis` và `numeric_sql_tool_v2` phải nằm **ngang hàng nhau** trong cùng 1 thư mục mẹ (Ví dụ cùng nằm trong `D:\javis_text2sql`). Đừng để thư mục này lồng vào bên trong thư mục kia.
3. **Câu hỏi RAG luôn báo "Không tìm thấy" ở lần chạy đầu tiên**:
   - Engine RAG (ChromaDB) lưu dữ liệu vector tĩnh trong folder `chroma_db` nội bộ. Nếu khi nén code bạn xóa folder này (như khuyến cáo ở Mục 1), hệ thống sẽ bị rỗng kiến thức. Khi đó bạn cần chạy script ingest dữ liệu (Data Ingestion Pipeline) để hệ thống nhúng (embed) lại các văn bản transcript vào ChromaDB trước khi chat.
