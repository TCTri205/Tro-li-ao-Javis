# 📊 Phân Tích Chi Tiết Database — Numeric SQL Tool

## 1. Tổng Quan Kiến Trúc

Hệ thống sử dụng **PostgreSQL 15** chạy qua Docker, phục vụ cho một chatbot trợ lý AI (Javis) chuyên xử lý **bản ghi cuộc họp (meeting transcripts)** bằng tiếng Nhật. Database có tên `app_db`, kết nối qua port `54331`.

```
NUMERIC_SQL_DATABASE_URL = postgresql://app_user:app_password@localhost:54331/app_db
```

Database được thiết kế theo kiến trúc **2 nhánh dữ liệu song song**:

```mermaid
graph TD
    subgraph "Nhánh Meeting Transcripts"
        T["transcripts"] --> CP["chunks_passage"]
        T --> CT["chunks_turn"]
        CP --> CT
    end
    
    subgraph "Nhánh Company Documents"
        CD["company_documents"] --> CC["company_chunks"]
    end
    
    subgraph "System"
        AV["alembic_version"]
    end
```

---

## 2. Chi Tiết Từng Bảng

### 2.1. `alembic_version` — Quản lý migration

| Cột | Kiểu | Mô tả |
|-----|------|-------|
| `version_num` | `varchar(32)` PK | Phiên bản migration hiện tại |

> [!NOTE]
> Bảng này do Alembic (thư viện migration của Python/SQLAlchemy) tự quản lý. Nó lưu version number để biết schema đang ở trạng thái nào.

---

### 2.2. `transcripts` — Bảng trung tâm: Bản ghi cuộc họp

Đây là **bảng quan trọng nhất**, lưu metadata + nội dung thô của mỗi cuộc họp/cuộc gọi.

| Cột | Kiểu | Mô tả |
|-----|------|-------|
| `id` | `uuid` PK | ID duy nhất cho transcript |
| `session_id` | `varchar(64)` UNIQUE | Mã phiên (VD: `GT_01`, `GT_02`) |
| `user_id` | `uuid` NOT NULL | ID người dùng sở hữu transcript |
| `meeting_date` | `date` NOT NULL | Ngày diễn ra cuộc họp |
| `participants` | `jsonb` NOT NULL | Danh sách người tham gia (JSON array) |
| `speaker_count` | `integer` | Số lượng người nói |
| `duration_seconds` | `integer` | Thời lượng cuộc họp (giây) |
| `content_hash` | `char(64)` NOT NULL | SHA-256 hash của nội dung để chống trùng lặp |
| `raw_text` | `text` NOT NULL | **Toàn bộ nội dung thô** của cuộc họp |
| `summary` | `text` | Tóm tắt nội dung |
| `summary_metadata` | `jsonb` | Metadata bổ sung cho summary (topics, entities) |
| `status` | `varchar(20)` NOT NULL | Trạng thái xử lý (`ready`, v.v.) |
| `error` | `text` | Lỗi nếu xử lý thất bại |
| `qdrant_synced` | `boolean` DEFAULT false | Đã đồng bộ lên Qdrant (vector DB) chưa |
| `ingest_tokens_in` | `integer` DEFAULT 0 | Số token đầu vào khi ingest |
| `ingest_tokens_out` | `integer` DEFAULT 0 | Số token đầu ra khi ingest |
| `created_at` | `timestamptz` | Thời điểm tạo |
| `updated_at` | `timestamptz` | Thời điểm cập nhật |
| `project_id` | `uuid` NOT NULL | ID dự án mà transcript thuộc về |

**Indexes trên bảng `transcripts`:**
- `ix_transcripts_project_date` → `(project_id, meeting_date)` — tìm theo project + ngày
- `ix_transcripts_user_date` → `(user_id, meeting_date)` — tìm theo user + ngày
- `ix_transcripts_user_project_date` → `(user_id, project_id, meeting_date)` — tìm kết hợp 3 chiều
- `ix_transcripts_sync` → partial index trên `qdrant_synced = false` — tìm nhanh bản chưa sync

> [!IMPORTANT]
> Dữ liệu seed hiện tại có **9 transcripts** (GT_01 → GT_09), tất cả thuộc cùng 1 user (`00000000-...`) và 1 project (`1a94c1ba-...`). Nội dung là các cuộc gọi điện thoại bằng **tiếng Nhật**, diễn ra từ 2026-05-01 đến 2026-05-09, thời lượng từ 25s đến 204s.

---

### 2.3. `chunks_passage` — Đoạn hội thoại (passage-level chunking)

Mỗi transcript được **chia thành các đoạn hội thoại (passages)** — đây là level chunking thô, gom nhiều lượt nói liên tiếp thành một đoạn có ngữ cảnh.

| Cột | Kiểu | Mô tả |
|-----|------|-------|
| `id` | `uuid` PK | ID đoạn |
| `transcript_id` | `uuid` FK → transcripts | Transcript chứa đoạn này |
| `passage_index` | `integer` NOT NULL | Thứ tự đoạn trong transcript (0-based) |
| `time_start_sec` | `integer` | Thời điểm bắt đầu (giây) |
| `time_end_sec` | `integer` | Thời điểm kết thúc (giây) |
| `speaker_list` | `jsonb` | Danh sách speakers trong đoạn |
| `text` | `text` NOT NULL | Nội dung toàn bộ đoạn (nhiều lượt nói) |
| `chunk_metadata` | `jsonb` NOT NULL | `{topics, entities, turn_types, importance_score}` |
| `importance_score` | `smallint` | Điểm quan trọng (1-5) |
| `enrich_error` | `text` | Lỗi khi enrichment |
| `qdrant_synced` | `boolean` DEFAULT false | Đã sync Qdrant chưa |
| `created_at` | `timestamptz` | Thời điểm tạo |

**Constraints:**
- UNIQUE `(transcript_id, passage_index)` — mỗi transcript không có 2 passage cùng index
- FK `transcript_id → transcripts(id) ON DELETE CASCADE`

> [!NOTE]
> Trong dữ liệu seed, mỗi transcript chỉ có **1 passage duy nhất** (passage_index = 0) chứa toàn bộ nội dung cuộc gọi. Trong thực tế, cuộc họp dài hơn sẽ được chia thành nhiều passages.

---

### 2.4. `chunks_turn` — Lượt nói (turn-level chunking)

Đây là **level chunking chi tiết nhất** — mỗi row là **một lượt phát biểu của một người nói**.

| Cột | Kiểu | Mô tả |
|-----|------|-------|
| `id` | `uuid` PK | ID lượt nói |
| `transcript_id` | `uuid` FK → transcripts | Transcript chứa lượt nói |
| `passage_id` | `uuid` FK → chunks_passage | Passage chứa lượt nói (nullable) |
| `turn_index` | `integer` NOT NULL | Thứ tự lượt nói trong transcript |
| `speaker` | `varchar(32)` NOT NULL | Tên/mã người nói |
| `time_start_sec` | `integer` NOT NULL | Thời điểm bắt đầu nói |
| `time_end_sec` | `integer` NOT NULL | Thời điểm kết thúc nói |
| `text` | `text` NOT NULL | Nội dung lượt nói |
| `sub_chunk_index` | `integer` DEFAULT 0 | Sub-index khi 1 turn quá dài cần chia nhỏ |
| `chunk_metadata` | `jsonb` NOT NULL | Metadata (topics, entities, turn_types, importance_score) |
| `importance_score` | `smallint` | Điểm quan trọng |
| `enrich_error` | `text` | Lỗi enrichment |
| `qdrant_synced` | `boolean` DEFAULT false | Đã sync Qdrant chưa |
| `created_at` | `timestamptz` | Thời điểm tạo |

**Constraints & Indexes:**
- UNIQUE `(transcript_id, turn_index, sub_chunk_index)` — định danh duy nhất
- FK `transcript_id → transcripts(id) ON DELETE CASCADE`
- FK `passage_id → chunks_passage(id) ON DELETE CASCADE`
- `ix_turn_speaker` → tìm theo speaker
- `ix_turn_passage` → tìm theo passage
- `ix_turn_transcript` → tìm theo transcript
- `ix_turn_metadata` → GIN index trên `chunk_metadata` (tìm trong JSON)

---

### 2.5. `company_documents` — Tài liệu công ty

Lưu trữ metadata về các tài liệu (PDF, Word, v.v.) được upload lên hệ thống.

| Cột | Kiểu | Mô tả |
|-----|------|-------|
| `id` | `uuid` PK | ID tài liệu |
| `filename` | `varchar(255)` NOT NULL | Tên file gốc |
| `content_type` | `varchar(255)` | MIME type (pdf, docx, v.v.) |
| `size_bytes` | `integer` NOT NULL | Dung lượng file |
| `stored_path` | `text` NOT NULL | Đường dẫn lưu trữ file |
| `content_hash` | `char(64)` UNIQUE | SHA-256 để chống trùng |
| `status` | `varchar(20)` NOT NULL | Trạng thái xử lý |
| `page_count` | `integer` | Số trang |
| `raw_text` | `text` | Text trích xuất từ tài liệu |
| `summary` | `text` | Tóm tắt nội dung |
| `qdrant_synced` | `boolean` DEFAULT false | Đã sync Qdrant chưa |
| `created_at` | `timestamptz` | Thời điểm tạo |

---

### 2.6. `company_chunks` — Chunk tài liệu công ty

Chia tài liệu thành các đoạn nhỏ để phục vụ search/RAG.

| Cột | Kiểu | Mô tả |
|-----|------|-------|
| `id` | `uuid` PK | ID chunk |
| `document_id` | `uuid` FK → company_documents | Tài liệu gốc |
| `chunk_index` | `integer` NOT NULL | Thứ tự chunk |
| `page_number` | `integer` | Trang chứa chunk |
| `section_title` | `text` | Tiêu đề section |
| `text` | `text` NOT NULL | Nội dung chunk |
| `chunk_metadata` | `jsonb` | Metadata bổ sung |
| `enrich_error` | `text` | Lỗi enrichment |
| `qdrant_synced` | `boolean` DEFAULT false | Đã sync Qdrant chưa |
| `created_at` | `timestamptz` | Thời điểm tạo |

> [!NOTE]
> Trong dữ liệu seed, 2 bảng `company_documents` và `company_chunks` **chưa có dữ liệu** (file SQL rỗng). Nhánh này có vẻ đang trong giai đoạn phát triển.

---

## 3. Mối Quan Hệ Giữa Các Bảng (ERD)

```mermaid
erDiagram
    transcripts ||--o{ chunks_passage : "1:N"
    transcripts ||--o{ chunks_turn : "1:N"
    chunks_passage ||--o{ chunks_turn : "1:N (optional)"
    company_documents ||--o{ company_chunks : "1:N"
    
    transcripts {
        uuid id PK
        varchar session_id UK
        uuid user_id
        date meeting_date
        jsonb participants
        integer duration_seconds
        text raw_text
        text summary
        uuid project_id
    }
    
    chunks_passage {
        uuid id PK
        uuid transcript_id FK
        integer passage_index
        integer time_start_sec
        integer time_end_sec
        text text
        jsonb chunk_metadata
    }
    
    chunks_turn {
        uuid id PK
        uuid transcript_id FK
        uuid passage_id FK
        integer turn_index
        varchar speaker
        integer time_start_sec
        integer time_end_sec
        text text
        jsonb chunk_metadata
    }
    
    company_documents {
        uuid id PK
        varchar filename
        integer size_bytes
        text raw_text
        text summary
    }
    
    company_chunks {
        uuid id PK
        uuid document_id FK
        integer chunk_index
        text text
        jsonb chunk_metadata
    }
```

---

## 4. Chiến Lược Chunking — 3 Tầng

Hệ thống áp dụng mô hình **chunking 3 tầng** cho meeting transcripts:

```
┌─────────────────────────────────────────────────┐
│  TRANSCRIPT (raw_text)                          │  ← Toàn bộ cuộc họp
│  duration: 204s, speakers: 2                    │
├─────────────────────────────────────────────────┤
│  PASSAGE 0                    │  PASSAGE 1      │  ← Gom nhóm theo ngữ cảnh
│  time: 0s → 120s              │  120s → 204s    │
│  speakers: [A, B]             │  speakers: [A]  │
├──────────┬──────────┬─────────┼─────────────────┤
│  TURN 0  │  TURN 1  │ TURN 2  │  TURN 3  │ ... │  ← Từng lượt nói
│  A: "..." │  B: "..." │ A: "..." │  A: "..." │    │
│  0-3s    │  3-7s    │  7-9s   │  120-125s │     │
└──────────┴──────────┴─────────┴──────────┴─────┘
```

**Mục đích:**
- **Transcript level**: Metadata tổng quan, dùng cho aggregation (count, sum, avg)
- **Passage level**: Đoạn ngữ cảnh trung bình, dùng cho semantic search (RAG via Qdrant)
- **Turn level**: Chi tiết nhất, dùng cho tìm kiếm chính xác theo speaker/nội dung

---

## 5. Tích Hợp Qdrant (Vector DB)

Mọi bảng dữ liệu chính đều có cột `qdrant_synced`:

| Bảng | Ý nghĩa |
|------|---------|
| `transcripts` | Summary được vector hóa để semantic search |
| `chunks_passage` | Đoạn passage được embed để RAG |
| `chunks_turn` | Turn được embed cho granular search |
| `company_documents` | Summary tài liệu được embed |
| `company_chunks` | Chunk tài liệu được embed |

> [!TIP]
> Partial index `ix_transcripts_sync WHERE qdrant_synced = false` giúp nhanh chóng tìm các bản ghi **chưa sync** để batch sync lên Qdrant, tránh quét toàn bộ bảng.

---

## 6. Pipeline Xử Lý — Numeric SQL Tool

Hệ thống `numeric_sql_tool` hoạt động như một **công cụ truy vấn số liệu từ ngôn ngữ tự nhiên (tiếng Nhật)**:

```mermaid
flowchart LR
    Q["Câu hỏi tiếng Nhật"] --> H["Heuristic\n(regex rules)"]
    Q --> L["LLM (Groq)\n(Llama 3.3 70B)"]
    H --> I["NumericIntent\n{operator, target,\ngroup_by, filter}"]
    L --> I
    I --> B["SQL Builder"]
    B --> P["PostgreSQL"]
    P --> R["NumericResult\n{rows, metadata}"]
```

**NumericIntent** có 4 trường:
- `operator`: `sum | avg | max | min | count | skip`
- `target`: `duration_seconds | meeting_count`
- `group_by`: `none | user_id | day | speaker`
- `context_filter`: chuỗi tìm kiếm trong summary/raw_text

**Ví dụ:**
| Câu hỏi | operator | target | group_by |
|----------|----------|--------|----------|
| 今月何件会議がありましたか？ | count | meeting_count | none |
| 5月の平均会議時間は？ | avg | duration_seconds | none |
| 日ごとの会議数は？ | count | meeting_count | day |
| 最も長い会議は？ | max | duration_seconds | none |

---

## 7. Dữ Liệu Seed Hiện Tại

| Session | Ngày | Speakers | Thời lượng | Nội dung chính |
|---------|------|----------|-----------|----------------|
| GT_01 | 2026-05-01 | 2 | 102s | Xác nhận gửi tài liệu cho Umeda, hỏi về công ty Three Luster |
| GT_02 | 2026-05-02 | 2 | 80s | Gọi tìm Ishida (bộ phận PMG), để lại SĐT gọi lại |
| GT_03 | 2026-05-03 | 2 | 204s | Khách hàng Shimada hỏi về bất động sản trước mặt, muốn xem nhà |
| GT_04 | 2026-05-04 | 2 | 105s | Ngân hàng Mitsubishi UFJ gọi tìm nhân viên Nakahara Rinka |
| GT_05 | 2026-05-05 | 2 | 34s | Xác nhận lịch họp: 14日 thứ 4, 10h |
| GT_06 | 2026-05-06 | 2 | 25s | AJ Technologies gọi tìm Kase, đã ra ngoài |
| GT_07 | 2026-05-07 | 2 | 28s | Xác nhận lịch họp: 14日 thứ 4, 10h (giống GT_05) |
| GT_08 | 2026-05-08 | 2 | 36s | AJ Technologies gọi tìm Onoda (đại lý bảo hiểm) |
| GT_09 | 2026-05-09 | 2 | 46s | Asset Japan gọi cơ quan thanh toán trung ương, nhắn tin cho Yamauchi |

**Tổng cộng:** 9 transcripts, tất cả 2 speakers, thời lượng 25s → 204s, ngày 01-09/05/2026.

---

## 8. Bảo Mật & Cơ Chế An Toàn

- **READ ONLY transactions**: Mọi query numeric đều chạy trong transaction `SET TRANSACTION READ ONLY`
- **Statement timeout**: Mặc định 5000ms (5 giây), ngăn query chạy quá lâu
- **User isolation**: Pipeline luôn filter theo `user_id`, ngăn user xem data của người khác
- **`allow_cross_user` flag**: Mặc định `false`, chặn aggregate theo user_id
- **`set_config('app.current_user_id', ...)` **: Ghi nhận user hiện tại vào session config cho RLS nếu cần

---

## 9. Indexing Strategy

| Index | Kiểu | Bảng | Cột | Mục đích |
|-------|------|------|-----|----------|
| `ix_transcripts_project_date` | B-tree | transcripts | (project_id, meeting_date) | Lọc theo project + thời gian |
| `ix_transcripts_user_date` | B-tree | transcripts | (user_id, meeting_date) | Lọc theo user + thời gian |
| `ix_transcripts_user_project_date` | B-tree | transcripts | (user_id, project_id, meeting_date) | Composite query 3 chiều |
| `ix_transcripts_sync` | B-tree (partial) | transcripts | qdrant_synced WHERE false | Tìm bản chưa sync |
| `ix_passage_transcript` | B-tree | chunks_passage | transcript_id | Join passage ↔ transcript |
| `ix_passage_metadata` | GIN | chunks_passage | chunk_metadata | Tìm kiếm trong JSON metadata |
| `ix_turn_transcript` | B-tree | chunks_turn | transcript_id | Join turn ↔ transcript |
| `ix_turn_passage` | B-tree | chunks_turn | passage_id | Join turn ↔ passage |
| `ix_turn_speaker` | B-tree | chunks_turn | speaker | Lọc/group theo speaker |
| `ix_turn_metadata` | GIN | chunks_turn | chunk_metadata | Tìm kiếm trong JSON metadata |
| `ix_company_chunks_doc` | B-tree | company_chunks | document_id | Join chunk ↔ document |

> [!TIP]
> GIN index trên `chunk_metadata` cho phép query nhanh kiểu `chunk_metadata @> '{"topics": ["budget"]}'` — rất hữu ích cho filtering theo chủ đề/entity.
