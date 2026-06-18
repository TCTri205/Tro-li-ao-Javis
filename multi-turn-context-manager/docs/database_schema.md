# Thiết kế Lược đồ Cơ sở dữ liệu (Database Schema)

## 1. Lưu trữ vĩnh viễn (Persistent Cold Storage)

### Bảng `transcripts`
Lưu trữ nhật ký cuộc gọi và siêu dữ liệu (metadata) của tài liệu.

| Tên cột | Kiểu dữ liệu | Ràng buộc |
| :--- | :--- | :--- |
| `id` | `UUID` | PRIMARY KEY |
| `session_id` | `VARCHAR(64)` | INDEX (GT_XX session format) |
| `meeting_date` | `DATE` | |
| `participants` | `JSONB` | Danh sách người tham gia |
| `speaker_count` | `INT` | Số lượng người nói |
| `duration_seconds`| `INT` | Thời lượng cuộc gọi (giây) |
| `raw_text` | `TEXT` | Nội dung hội thoại thô |
| `summary` | `TEXT` | Tóm tắt cuộc gọi |

### Bảng `chunks_turn`
Lưu trữ các phân đoạn hội thoại theo lượt nói.

| Tên cột | Kiểu dữ liệu | Ràng buộc |
| :--- | :--- | :--- |
| `id` | `UUID` | PRIMARY KEY |
| `transcript_id` | `UUID` | REFERENCES `transcripts`(id) |
| `turn_index` | `INT` | Thứ tự lượt nói |
| `speaker` | `VARCHAR` | Tên người nói |
| `time_start_sec` | `INT` | Thời điểm bắt đầu (giây) |
| `time_end_sec` | `INT` | Thời điểm kết thúc (giây) |
| `text` | `TEXT` | Nội dung phát ngôn |

### Bảng `company_chunks`
Lưu trữ các kiến thức bổ sung về công ty cho RAG.

| Tên cột | Kiểu dữ liệu | Ràng buộc |
| :--- | :--- | :--- |
| `id` | `UUID` | PRIMARY KEY |
| `document_id` | `UUID` | |
| `text` | `TEXT` | Nội dung kiến thức |

### Bảng `chat_history`
Lưu trữ lịch sử hội thoại của người dùng và trợ lý.

| Tên cột | Kiểu dữ liệu | Ràng buộc |
| :--- | :--- | :--- |
| `id` | `BIGSERIAL` | PRIMARY KEY |
| `session_id` | `VARCHAR(64)` | INDEX |
| `role` | `VARCHAR(20)` | user, assistant |
| `content` | `TEXT` | Nội dung tin nhắn |
| `rewritten_content`| `TEXT` | Truy vấn đã viết lại (chỉ user) |
| `answer_confidence`| `VARCHAR(20)` | high, low |
| `routing_metadata` | `JSONB` | Thông tin định tuyến |
| `created_at` | `TIMESTAMP` | |

## 2. Bộ nhớ đệm ngữ cảnh động (Dynamic Context Cache)

### `session_context_cache` (Bảng Hot)
Duy trì siêu dữ liệu để tìm kiếm và định tuyến nhanh chóng.

| Tên cột | Kiểu dữ liệu | Ràng buộc |
| :--- | :--- | :--- |
| `id` | `BIGSERIAL` | PRIMARY KEY |
| `session_id` | `VARCHAR(64)` | NOT NULL, INDEX |
| `topic_key` | `TEXT` | NOT NULL (e.g., sql_123, GT_04) |
| `last_pipeline` | `VARCHAR(50)` | SQL, RAG, WEB, MODEL |
| `last_routing_method` | `VARCHAR(50)` | heuristics, embeddings, llm_router |
| `query_embedding` | `vector(384)` | pgvector (multilingual-e5-small) |
| `embedding_model_version` | `VARCHAR(50)` | default: 'multilingual-e5-small' |
| `last_accessed_at` | `TIMESTAMP` | Cập nhật khi Hit (LRU policy) |
| `refreshed_at` | `TIMESTAMP` | Cập nhật khi truy xuất Engine (TTL policy) |

### `session_context_payload` (Bảng Cold)
Lưu trữ dữ liệu JSON lớn và chỉ được tải khi cần thiết.

| Tên cột | Kiểu dữ liệu | Ràng buộc |
| :--- | :--- | :--- |
| `cache_id` | `BIGINT` | PRIMARY KEY, REFERENCES `session_context_cache`(id) ON DELETE CASCADE |
| `cached_payload` | `JSONB` | SQL rows, RAG chunks, Web snippets |
| `summary_context` | `JSONB` | Metadata tóm tắt (entity_type, entity_id, display_name) |

## 3. Chỉ mục thực thể (Entity Index)

### `session_entity_index`
Ánh xạ nhanh các đại từ và tên thực thể để giải quyết Coreference (Tier 1).

| Tên cột | Kiểu dữ liệu | Ràng buộc |
| :--- | :--- | :--- |
| `session_id` | `VARCHAR(64)` | NOT NULL, INDEX |
| `entity_id` | `TEXT` | Định danh duy nhất (e.g., GT_04, Person_Name) |
| `entity_type` | `VARCHAR(50)` | meeting_transcript, person, document, sql_result |
| `display_names` | `TEXT[]` | Mảng các đại từ và tên hiển thị (GIN INDEX) |
| `cache_slot_id` | `BIGINT` | REFERENCES `session_context_cache`(id) |

**Constraint:** `UNIQUE (session_id, entity_id)` để hỗ trợ cơ chế UPSERT.

## 4. Các điểm tối ưu hóa chính (Key Optimizations)

*   **Phân tách Hot/Cold:** metadata nhẹ nằm ở bảng Hot để pgvector search nhanh, dữ liệu nặng nằm ở bảng Cold để tránh phình bộ nhớ khi quét index.
*   **Chỉ mục GIN:** Áp dụng cho `display_names` giúp tra cứu đại từ chỉ định ("nó", "người đó") cực nhanh qua toán tử `@>`.
*   **LRU Limit:** Hệ thống giới hạn 3 slot cache trên mỗi `session_id` thông qua kiểm tra số lượng bản ghi trước khi chèn mới trong `upsert_cache_slot`.
*   **Transaction Advisory Locks:** Sử dụng `pg_try_advisory_xact_lock(bigint)` để đảm bảo chỉ một tiến trình được xử lý một phiên tại một thời điểm.
