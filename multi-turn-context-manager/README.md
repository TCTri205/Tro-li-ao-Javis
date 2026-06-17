# Multi-Turn Context Manager (V1.0.0)

Hệ thống quản lý ngữ cảnh đa lượt (Multi-turn Context Management) hiệu năng cao dành cho trợ lý AI (Javis). Đây là lớp trung gian thông minh kết nối truy vấn của người dùng với nhiều nguồn dữ liệu (SQL, RAG, Web) trong khi vẫn duy trì tính nhất quán của ngữ cảnh qua các phiên làm việc.

## 🚀 Tính năng then chốt (Key Features)

- **Định tuyến thông minh 2 lớp (2-Tier Routing):**
  - **Tier 1 (Fast Path):** Sử dụng Heuristics, Entity Index và pgvector để giải quyết các câu hỏi tiếp nối và đại từ (ví dụ: "nó", "cuộc gọi đó") với độ trễ < 15ms.
  - **Tier 2 (Precision Path):** Sử dụng LLM (Groq/Javis Qwen) để phân tích ý định phức tạp, viết lại truy vấn và giải quyết quy chiếu (Co-reference).
- **Quản lý ngữ cảnh nâng cao:**
  - **Hot/Cold Storage:** Tách biệt siêu dữ liệu nhẹ (Hot) và dữ liệu tải trọng lớn (Cold) trong PostgreSQL để tối ưu hóa bộ nhớ.
  - **LRU Cache Eviction:** Duy trì tối đa 3 slot cache nóng nhất cho mỗi phiên.
  - **Entity Indexing:** Tự động theo dõi các thực thể (mã cuộc gọi, ngày tháng, tên người) để giải quyết đại từ chỉ định ngay lập tức.
- **Công cụ thực thi linh hoạt (Execution Engines):**
  - **SQL Engine:** Chuyển đổi ngôn ngữ tự nhiên thành SQL để truy xuất dữ liệu có cấu trúc.
  - **RAG Engine:** Tìm kiếm vector trên tài liệu phi cấu trúc bằng `pgvector`.
  - **Web Engine:** Cập nhật kiến thức thời gian thực qua tìm kiếm web.
- **Ngăn chặn ảo giác (Hallucination Prevention):**
  - **Self-Check Verification:** Mọi câu trả lời của AI đều được đối chiếu với ngữ cảnh thô đã truy xuất để đảm bảo tính xác thực 100%.
- **Tính ổn định hệ thống:**
  - **Advisory Locking:** Sử dụng khóa cố vấn 64-bit để ngăn chặn tình trạng Race Condition.
  - **Circuit Breakers:** Tự động dự phòng khi gặp sự cố embedding hoặc timeout LLM.

## 🏗️ Kiến trúc hệ thống (Vòng đời 8 bước)

1.  **Request Input & Locking:** Nhận truy vấn và lấy khóa Advisory Lock cấp phiên.
2.  **Routing (Tier 1 & 2):** Xác định mục tiêu (Hit/Shift) và viết lại truy vấn.
3.  **Execution & Retrieval:** Thực thi các engine (SQL/RAG/Web) để lấy dữ liệu.
4.  **Metadata Extraction:** Trích xuất thực thể và chuẩn bị tóm tắt ngữ cảnh.
5.  **Cache Orchestration:** Cập nhật Hot/Cold storage và thực hiện LRU.
6.  **Answer Generation:** Tạo câu trả lời qua LLM hoặc luồng phản hồi trực tiếp (Direct Path).
7.  **Self-Check Verification:** Xác minh hiện tượng ảo giác và tính nhất quán.
8.  **Logging & Commit:** Lưu nhật ký, metadata và commit giao dịch trước khi giải phóng Lock.

## 📥 Đầu vào & 📤 Đầu ra

### Input Schema
| Trường | Kiểu | Mô tả |
| :--- | :--- | :--- |
| `session_id` | `String` | Định danh duy nhất của phiên (ví dụ: GT_01). |
| `query` | `String` | Truy vấn ngôn ngữ tự nhiên (tiếng Việt hoặc tiếng Nhật). |

### Output Schema
| Trường | Kiểu | Mô tả |
| :--- | :--- | :--- |
| `answer` | `String` | Câu trả lời cuối cùng (đã qua kiểm tra xác minh). |
| `metadata` | `Object` | Thông tin kỹ thuật: `latency_ms`, `routing_method`, `target_pipeline`, v.v. |

## 🛠️ Cài đặt và Thiết lập

### Yêu cầu hệ thống
- Python 3.11+
- PostgreSQL 15+ (đã cài `pgvector` và `uuid-ossp`).
- Quyền truy cập API LLM (Groq/Athena).

### Các bước cài đặt
1.  **Clone repository:**
    ```bash
    git clone <repo-url>
    cd multi-turn-context-manager
    ```
2.  **Thiết lập môi trường ảo:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # Hoặc .venv\Scripts\activate trên Windows
    pip install -r requirements.txt
    ```
3.  **Cấu hình:**
    Tạo tệp `.env` từ mẫu `.env.example` và cung cấp thông tin kết nối DB cũng như API keys.
4.  **Khởi tạo cơ sở dữ liệu:**
    ```bash
    python scripts/init_db.py
    python scripts/init_extra_tables.py
    ```

## 🧪 Kiểm thử
Hệ thống đi kèm bộ kiểm thử E2E toàn diện bao gồm các kịch bản Tiêu chuẩn, Tiêu cực và Khôi phục.

```bash
python tests/test_suite.py
```

---
*Phát triển bởi Gemini CLI Agent cho dự án Trợ lý ảo Javis.*
