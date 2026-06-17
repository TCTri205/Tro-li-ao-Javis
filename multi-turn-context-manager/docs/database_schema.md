# Thiết kế Lược đồ Cơ sở dữ liệu (Database Schema)

## 1. Lưu trữ vĩnh viễn (Persistent Cold Storage)

### Bảng `transcripts`
Lưu trữ nhật ký cuộc gọi và siêu dữ liệu (metadata) của tài liệu (lược đồ hiện có).

| Tên cột | Kiểu dữ liệu | Ràng buộc |
| :--- | :--- | :--- |
| `id` | `UUID` | PRIMARY KEY |
| `session_id` | `VARCHAR(64)` | INDEX |
| `meeting_date` | `DATE` | |
| `participants` | `JSONB` | |

## 2. Bộ nhớ đệm ngữ cảnh động (Dynamic Context Cache)

### `session_context_cache` (Bảng Hot)
Duy trì siêu dữ liệu để tìm kiếm và định tuyến nhanh chóng.

| Tên cột | Kiểu dữ liệu | Ràng buộc |
| :--- | :--- | :--- |
| `id` | `BIGSERIAL` | PRIMARY KEY |
| `session_id` | `VARCHAR(64)` | NOT NULL, INDEX |
| `topic_key` | `TEXT` | NOT NULL |
| `last_pipeline` | `VARCHAR(50)` | SQL, RAG, WEB, MODEL |
| `query_embedding` | `vector(384)` | pgvector |
| `last_accessed_at` | `TIMESTAMP` | Dấu thời gian dùng cho LRU |
| `refreshed_at` | `TIMESTAMP` | Dấu thời gian dùng cho TTL |

### `session_context_payload` (Bảng Cold)
Lưu trữ dữ liệu JSON lớn và chỉ được tải khi cần thiết.

| Tên cột | Kiểu dữ liệu | Ràng buộc |
| :--- | :--- | :--- |
| `cache_id` | `BIGINT` | REFERENCES Hot Table (CASCADE) |
| `cached_payload` | `JSONB` | SQL rows, RAG chunks, Web snippets |
| `summary_context` | `JSONB` | Tóm tắt hỗ trợ định tuyến |

## 3. Chỉ mục thực thể (Entity Index)

### `session_entity_index`
Ánh xạ nhanh các đại từ và tên thực thể.

| Tên cột | Kiểu dữ liệu | Ràng buộc |
| :--- | :--- | :--- |
| `session_id` | `VARCHAR(64)` | NOT NULL, INDEX |
| `entity_id` | `TEXT` | Định danh duy nhất của thực thể |
| `entity_type` | `VARCHAR(50)` | person, document, v.v. |
| `display_names` | `TEXT[]` | Mảng các đại từ chỉ định (GIN INDEX) |
| `cache_slot_id` | `BIGINT` | Slot cache mục tiêu |

## 4. Các điểm tối ưu hóa chính (Key Optimizations)

*   **Phân tách Hot/Cold:** Bằng cách tách biệt siêu dữ liệu (Hot) và dữ liệu tải trọng lớn (Cold), hiệu quả bộ nhớ của PostgreSQL được tối đa hóa và tránh được việc quét toàn bộ bảng (Seq Scan).
*   **Chỉ mục GIN:** Áp dụng chỉ mục GIN cho cột `display_names` (mảng TEXT) giúp việc đối chiếu đại từ có thể thực hiện được trong thời gian không đổi (constant time).
*   **Advisory Locks:** Kiểm soát việc thực thi đồng thời các yêu cầu đối với cùng một phiên ở cấp độ cơ sở dữ liệu để đảm bảo tính nhất quán của bộ nhớ đệm.
