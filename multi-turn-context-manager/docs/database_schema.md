# Thiết Kế Cơ Sở Dữ Liệu (Database Schema Design)
## Quản Lý Ngữ Cảnh Hội Thoại Đa Lượt (Multi-turn Context Management)

Hệ thống sử dụng cơ sở dữ liệu **PostgreSQL** để lưu trữ cả lịch sử hội thoại (Chat History) và trạng thái cache ngữ cảnh (Context Cache) v3. Lược đồ dữ liệu này áp dụng thiết kế phân tách Hot/Cold table nhằm giải quyết triệt để vấn đề phình dòng dữ liệu (row bloat) và cải thiện hiệu năng truy vấn.

---

```sql
-- Kích hoạt extension uuid-ossp (nếu cần sinh UUID tự động)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- Kích hoạt extension vector phục vụ tìm kiếm ngữ nghĩa (pgvector)
CREATE EXTENSION IF NOT EXISTS vector;

-- =========================================================================
-- BẢNG 1: CHAT HISTORY (Lưu trữ lịch sử hội thoại giữa User và AI Assistant)
-- =========================================================================
CREATE TABLE chat_history (
    id                BIGSERIAL PRIMARY KEY,
    session_id        VARCHAR(64) NOT NULL,
    role              VARCHAR(50) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content           TEXT NOT NULL,
    rewritten_content TEXT, -- Lưu câu hỏi đã được làm rõ (phục vụ debug/analytics)
    answer_confidence VARCHAR(50) NOT NULL CHECK (answer_confidence IN ('high', 'low')) DEFAULT 'high', -- Cờ xác định độ tin cậy của câu trả lời
    routing_metadata  JSONB, -- Lưu trữ thông tin routing_method, embedding_failed, v.v.
    created_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Tạo chỉ mục để truy vấn lịch sử nhanh theo session và thời gian tăng dần
CREATE INDEX idx_chat_history_session_time 
ON chat_history (session_id, created_at ASC);


-- =========================================================================
-- BẢNG 2: SESSION CONTEXT CACHE (Bảng HOT - Chỉ lưu Metadata gọn nhẹ)
-- =========================================================================
CREATE TABLE session_context_cache (
    id                      BIGSERIAL PRIMARY KEY,
    session_id              VARCHAR(64) NOT NULL,
    topic_key               TEXT NOT NULL,          -- Nhãn định danh của chủ đề
    last_pipeline           VARCHAR(50) NOT NULL CHECK (last_pipeline IN ('RAG', 'SQL', 'WEB', 'MODEL')),
    last_routing_method     VARCHAR(50) NOT NULL CHECK (last_routing_method IN ('heuristics', 'embeddings', 'llm_router', 'fallback')), -- Cách thức định tuyến cuối
    query_embedding         vector(384),            -- Vector embedding của rewritten_query (dùng e5-small)
    embedding_model_version VARCHAR(100),           -- Version model sinh embedding để kiểm soát tương thích
    last_accessed_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP, -- Dùng cho LRU eviction
    refreshed_at            TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP, -- Dùng cho TTL freshness
    UNIQUE (session_id, topic_key)
);

-- Chỉ mục phức hợp để truy vấn nhanh metadata cache theo session và topic
CREATE INDEX idx_context_cache_session_topic 
ON session_context_cache (session_id, topic_key);

-- Chỉ mục cho thời gian truy cập phục vụ LRU eviction
CREATE INDEX idx_context_cache_last_accessed 
ON session_context_cache (last_accessed_at);

-- GHI CHÚ: Không tạo chỉ mục IVFFlat/HNSW cho query_embedding vì mỗi session chỉ có tối đa 3 slots hoạt động song song.
-- Việc tìm kiếm tương đồng cosine được thực hiện nhanh bằng phương pháp brute-force trên tập kết quả sau khi đã lọc theo session_id (sử dụng idx_context_cache_session_topic B-tree).

-- Chỉ mục riêng phục vụ kiểm tra TTL nhanh cho pipeline WEB (Partial Index)
CREATE INDEX idx_context_cache_web_refreshed 
ON session_context_cache (refreshed_at) 
WHERE last_pipeline = 'WEB';


-- =========================================================================
-- BẢNG 3: SESSION CONTEXT PAYLOAD (Bảng COLD - Lưu payload JSON kích thước lớn)
-- =========================================================================
CREATE TABLE session_context_payload (
    id              BIGSERIAL PRIMARY KEY,
    cache_id        BIGINT NOT NULL REFERENCES session_context_cache(id) ON DELETE CASCADE,
    cached_payload  JSONB NOT NULL,         -- Lưu dữ liệu thô tùy biến (SQL rows, RAG chunks, Web snippets)
    summary_context JSONB,                  -- Tóm tắt ngữ cảnh thực thể dạng JSON cấu trúc
    UNIQUE (cache_id)
);

-- Chỉ mục khóa ngoại giúp truy vấn kết nối nhanh
CREATE INDEX idx_context_payload_cache_id 
ON session_context_payload (cache_id);


-- =========================================================================
-- BẢNG 4: SESSION ENTITY INDEX (Ánh xạ pronoun tiếng Việt với cache slot ID)
-- =========================================================================
CREATE TABLE session_entity_index (
    id              BIGSERIAL PRIMARY KEY,
    session_id      VARCHAR(64) NOT NULL,
    entity_id       TEXT NOT NULL,          -- Ví dụ: "GT_04_yokobori_nakahara"
    entity_type     VARCHAR(50) NOT NULL CHECK (entity_type IN ('meeting_transcript', 'person', 'document', 'sql_result')),   -- Phân loại thực thể
    display_names   TEXT[] NOT NULL,        -- Các tên gọi/đại từ đại diện: {"cuộc gọi lúc nãy", "cuộc gọi ngày 4/5", "nó", "người đó", "ấy"}
    cache_slot_id   BIGINT REFERENCES session_context_cache(id) ON DELETE CASCADE,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (session_id, entity_id)
);

-- Tạo chỉ mục GIN trên display_names để tìm kiếm phần tử mảng nhanh chóng
CREATE INDEX idx_entity_index_display_names 
ON session_entity_index USING gin (display_names);

-- Chỉ mục lookup nhanh entity theo session và type
CREATE INDEX idx_entity_index_session_type 
ON session_entity_index (session_id, entity_type);
```

---

## 2. Chi Tiết Các Trường Dữ Liệu (Field Descriptions)

### 2.1. Bảng `chat_history`
| Tên Cột | Kiểu Dữ Liệu | Ràng Buộc | Mô Tả |
| :--- | :--- | :--- | :--- |
| `id` | `BIGSERIAL` | PRIMARY KEY | ID tự tăng, khóa chính. |
| `session_id` | `VARCHAR(64)` | NOT NULL | Định danh phiên hội thoại của người dùng (đồng bộ độ dài với bảng transcripts). |
| `role` | `VARCHAR(50)` | NOT NULL | Vai trò gửi tin nhắn: `user`, `assistant`, `system`. |
| `content` | `TEXT` | NOT NULL | Nội dung tin nhắn thô (Raw message). |
| `rewritten_content` | `TEXT` | NULL | Câu hỏi của user sau khi qua bộ viết lại ngữ cảnh. |
| `answer_confidence` | `VARCHAR(50)` | DEFAULT 'high' | Xác định độ tin cậy của câu trả lời (`high` hoặc `low`). |
| `routing_metadata` | `JSONB` | NULL | Chứa thông tin bổ trợ như `routing_method`, `embedding_failed`. |
| `created_at` | `TIMESTAMP` | DEFAULT NOW | Thời điểm tạo tin nhắn. |

### 2.2. Bảng `session_context_cache` (Hot Table)
| Tên Cột | Kiểu Dữ Liệu | Ràng Buộc | Mô Tả |
| :--- | :--- | :--- | :--- |
| `id` | `BIGSERIAL` | PRIMARY KEY | Khóa chính tự tăng. |
| `session_id` | `VARCHAR(64)` | NOT NULL | Định danh phiên hội thoại. |
| `topic_key` | `TEXT` | NOT NULL | Nhãn định danh chủ đề (phực vụ switch back). |
| `last_pipeline` | `VARCHAR(50)` | NOT NULL | Engine sử dụng gần nhất (`RAG`, `SQL`, `WEB`, `MODEL`). |
| `last_routing_method` | `VARCHAR(50)` | NOT NULL | Phương pháp định tuyến cuối: `heuristics`, `embeddings`, `llm_router`, `fallback`. |
| `query_embedding` | `vector(384)` | NULL | Vector embedding của câu hỏi đã được viết lại, dùng cho tìm kiếm tương đồng ngữ nghĩa. |
| `embedding_model_version`| `VARCHAR(100)`| NULL | Phiên bản mô hình sinh vector phục vụ check tính tương thích chéo. |
| `last_accessed_at` | `TIMESTAMP` | DEFAULT NOW | Thời điểm truy cập (đọc/ghi) cuối cùng. Dùng cho LRU. |
| `refreshed_at` | `TIMESTAMP` | DEFAULT NOW | Thời điểm làm mới dữ liệu từ Engine. Dùng cho TTL. |

### 2.3. Bảng `session_context_payload` (Cold Table)
| Tên Cột | Kiểu Dữ Liệu | Ràng Buộc | Mô Tả |
| :--- | :--- | :--- | :--- |
| `id` | `BIGSERIAL` | PRIMARY KEY | Khóa chính tự tăng. |
| `cache_id` | `BIGINT` | NOT NULL, FK | Liên kết tới bảng `session_context_cache`. |
| `cached_payload` | `JSONB` | NOT NULL | Chứa kết quả thô của lượt tìm kiếm trước (chunks, SQL rows, snippets). |
| `summary_context` | `JSONB` | NULL | Thực thể chính đã cấu trúc hóa phục vụ Tier 1 routing. |

### 2.4. Bảng `session_entity_index` (Entity Resolution Table)
| Tên Cột | Kiểu Dữ Liệu | Ràng Buộc | Mô Tả |
| :--- | :--- | :--- | :--- |
| `id` | `BIGSERIAL` | PRIMARY KEY | Khóa chính tự tăng. |
| `session_id` | `VARCHAR(64)` | NOT NULL | Định danh phiên hội thoại. |
| `entity_id` | `TEXT` | NOT NULL | Định danh thực thể (ví dụ ID hoặc chuỗi định danh). |
| `entity_type` | `VARCHAR(50)` | NOT NULL, CHECK | Phân loại thực thể, giới hạn bởi check constraint: `meeting_transcript`, `person`, `document`, `sql_result`. |
| `display_names` | `TEXT[]` | NOT NULL | Mảng các cụm từ chỉ định thực thể này, bao gồm cả các đại từ thay thế thường gặp. |
| `cache_slot_id` | `BIGINT` | FK | Khóa ngoại trỏ đến cache slot sở hữu thực thể này. |
| `created_at` | `TIMESTAMP` | DEFAULT NOW | Thời điểm ghi nhận thực thể. |

---

## 3. Chiến Lược Lập Chỉ Mục & Tối Ưu Hóa (Indexing & Optimization)

### 3.1. Phân Tách Hot/Cold Table Tối Ưu Buffer Pool
* **Vấn đề của thiết kế v1:** Khi lưu payload JSONB lớn chứa hàng chục nghìn ký tự của tài liệu RAG hoặc hàng trăm dòng SQL chung với metadata, dung lượng mỗi dòng (row size) phình to. Khi PostgreSQL quét bảng để tìm kiếm metadata định tuyến hoặc thực hiện LRU eviction, nó phải load toàn bộ dòng lớn vào RAM (Buffer Pool), dẫn đến lãng phí RAM và làm giảm cache hit rate của DB.
* **Giải pháp v2/v3:** Metadata gọn nhẹ (Hot table) được lưu riêng, giúp PostgreSQL lưu giữ hàng triệu bản ghi metadata chỉ trong một phần nhỏ bộ nhớ RAM. Bảng Cold chứa JSONB lớn chỉ được truy vấn (`JOIN` hoặc fetch bằng `cache_id`) khi bộ định tuyến quyết định có **Cache Hit** (`use_cache = true`).

### 3.2. Chỉ mục Phức Hợp B-Tree trên `chat_history`
```sql
CREATE INDEX idx_chat_history_session_time ON chat_history (session_id, created_at ASC);
```
* Đảm bảo truy xuất lịch sử chat của một phiên cụ thể chỉ mất vài micro giây (O(log N)), phục vụ bước phân tích ngữ cảnh mà không gây Seq Scan.

### 3.3. Cơ Chế Xử Lý Đồng Thời Bằng Session Serialization & Advisory Lock
* **Hạn chế của SKIP LOCKED:** Sử dụng `FOR UPDATE SKIP LOCKED` ở database khiến các request song song gửi lên liên tục của cùng một session bị drop (bỏ qua) âm thầm. Điều này làm trải nghiệm người dùng rất kém khi mạng chập chờn hoặc click đúp.
* **Cơ chế Advisory Lock và Row Lock:**
  * Hệ thống chuyển sang sử dụng khóa giao dịch session ở tầng PostgreSQL thông qua Advisory Locks:
    ```sql
    -- Lock phiên dựa trên hash của session_id, chặn request sau và bắt phải xếp hàng chờ trong timeout 8s
    SELECT pg_try_advisory_xact_lock(hashtext($1));
    ```
  * Trong phạm vi giao dịch đã lấy Advisory Lock, nếu luồng đi vào nhánh truy xuất từng phần (`needs_retrieval == "partial"`), nó sẽ khóa dòng tại bảng Hot bằng câu lệnh:
    ```sql
    SELECT 1 FROM session_context_cache WHERE session_id = $1 AND topic_key = $2 FOR UPDATE;
    ```
  * Việc này ngăn chặn tuyệt đối tình trạng một tiến trình xử lý song song khác chạy lệnh giải phóng LRU xóa mất dòng cache slot này trong lúc Engine đang lấy thông tin bổ sung.

### 3.4. Dọn Dẹp Cache Tự Động & Chiến Lược Eviction (LRU Eviction)
Hệ thống giới hạn tối đa **3 slots cache** cho mỗi `session_id` để tối ưu dung lượng:
1. Khi có topic mới được tạo ra, hệ thống đếm số lượng slot hiện tại của session trong bảng `session_context_cache`.
2. Nếu số lượng slot đạt 3, dòng có `last_accessed_at` cũ nhất sẽ bị xóa khỏi bảng Hot:
```sql
DELETE FROM session_context_cache
WHERE id = (
    SELECT id FROM session_context_cache
    WHERE session_id = $1
    ORDER BY last_accessed_at ASC
    LIMIT 1
);
```
3. Nhờ ràng buộc `ON DELETE CASCADE` ở khóa ngoại `cache_id` của bảng Cold `session_context_payload`, payload tương ứng sẽ tự động bị xóa sạch khỏi đĩa mà không cần câu lệnh xóa thứ hai.
4. Một cronjob chạy nền dọn dẹp các cache quá hạn (không hoạt động > 1 giờ):
```sql
DELETE FROM session_context_cache 
WHERE last_accessed_at < NOW() - INTERVAL '1 hour';
```
 Chỉ mục `idx_context_cache_last_accessed` đảm bảo câu lệnh này thực thi tức thời.
