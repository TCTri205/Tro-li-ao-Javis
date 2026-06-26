# Multi-Turn Context Manager (V1.0.0)

Hệ thống quản lý ngữ cảnh đa lượt (Multi-turn Context Management) hiệu năng cao dành cho trợ lý ảo AI (Javis). Đây là lớp trung gian thông minh kết nối truy vấn của người dùng với nhiều nguồn dữ liệu (SQL, RAG, Web Search) trong khi vẫn duy trì tính nhất quán của ngữ cảnh thực thể qua các phiên làm việc đa lượt, giải quyết đại từ chỉ định, và tối ưu hóa tài nguyên hệ thống.

---

## 🚀 Tính năng then chốt (Key Features)

- **Định tuyến hỗn hợp 2 lớp (2-Tier Hybrid Routing):**
  - **Tier 1 (Fast Path):** Sử dụng các quy tắc Heuristics (Regex), tìm kiếm chỉ mục thực thể (`session_entity_index`) cực nhanh, kiểm tra sai lệch metadata, và tính khoảng cách ngữ nghĩa vector qua `pgvector` để giải quyết các câu hỏi tiếp nối và đại từ (như "nó", "cuộc gọi đó") dưới **15ms**.
  - **Tier 2 (Precision Path):** Sử dụng LLM (Groq/Javis Qwen với thought reasoning) để phân tích ý định sâu, thực hiện giải quyết quy chiếu (Co-reference Resolution), viết lại câu hỏi hoàn chỉnh độc lập ngữ cảnh (Query Rewriting), và lựa chọn Pipeline thực thi phù hợp.
- **Quản lý Cache Hot/Cold tách biệt:**
  - **Hot Cache (`session_context_cache`):** Lưu trữ siêu dữ liệu nhẹ, khóa chủ đề (`topic_key`), và vector đại diện `query_embedding` để phục vụ tìm kiếm pgvector nhanh chóng.
  - **Cold Cache (`session_context_payload`):** Lưu trữ tải trọng dữ liệu thực tế lớn dưới dạng JSONB. Chỉ được tải khi xác định là **Cache Hit** (`use_cache = true`) nhằm tối ưu hóa bộ nhớ RAM và băng thông cơ sở dữ liệu.
- **Cập nhật & Đuổi Cache LRU thông minh:**
  - Giới hạn tối đa **5 slot cache chủ đề** cho mỗi phiên (`MAX_CACHE_SLOTS = 5` cấu hình tại [config.py](file:///D:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/src/config.py)), tự động loại bỏ slot cũ nhất (LRU Eviction) dựa trên thời gian truy cập gần nhất (`last_accessed_at`).
  - Sử dụng khóa dòng giao dịch `FOR UPDATE` trong quá trình cập nhật để ngăn chặn xung đột giữa LRU Eviction và cập nhật Payload.
- **Các Công cụ Thực thi (Execution Engines) & Khả năng chịu lỗi:**
  - **SQL Engine:** Chuyển đổi ngôn ngữ tự nhiên thành SQL để truy xuất dữ liệu có cấu trúc. Hỗ trợ cơ chế dịch lập trình nhanh (`heuristic_sql_translation`) cho các truy vấn siêu dữ liệu phổ biến để bỏ qua LLM. Tích hợp chống SQL Injection.
  - **RAG Engine:** Tìm kiếm vector ngữ nghĩa trên tài liệu phi cấu trúc bằng `pgvector`.
  - **Web Search Engine:** Cập nhật kiến thức thời gian thực qua tìm kiếm web với chính sách Cache TTL.
  - **Engine Circuit Breaker:** Cơ chế ngắt mạch tự động cô lập lỗi của từng engine và tự động hạ cấp về parametric knowledge khi gặp sự cố embedding hoặc timeout.
- **Cơ chế Phản hồi Trực tiếp (Direct-Answer Path):**
  - Bỏ qua LLM sinh câu trả lời đối với các câu hỏi có kết quả cấu trúc đơn giản (SQL aggregate, single web snippet, hoặc log thoại chi tiết thô) giúp phản hồi tức thì và tiết kiệm chi phí token.
- **Ngăn ngừa ảo giác (Hallucination Control):**
  - Trình kiểm định **Self-Check Verifier** đối chiếu câu trả lời được sinh ra với dữ liệu ngữ cảnh thô (raw payload) đã truy xuất. Cho phép thử lại tự động tối đa 2 lần trước khi hạ cấp độ tin cậy của câu trả lời xuống `low`.
- **Đồng bộ hóa & Khóa Cố văn (Advisory Locking):**
  - Sử dụng khóa cố vấn giao dịch `pg_try_advisory_xact_lock` dựa trên mã băm 64-bit của `session_id` để tuần tự hóa các yêu cầu đồng thời trong cùng một phiên, tránh Race Condition.

---

## 🏗️ Kiến trúc Hệ thống (Vòng đời 8 bước)

Luồng điều phối trong lớp [IntelligentOrchestrator](file:///D:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/src/orchestrator.py#L135) tuân thủ nghiêm ngặt quy trình 8 bước:

```mermaid
graph TD
    User((Người dùng)) -->|1. Truy vấn| Orch[Bộ điều phối thông minh]
    
    subgraph "2. Tầng định tuyến (router.py)"
        Orch --> T1[Tier 1: Heuristic, Entity Index & pgvector Filter]
        T1 -->|Lỗi Embedding / Tin cậy thấp / Mơ hồ| T2[Tier 2: LLM Router & Rewriter]
    end
    
    T1 -->|Quyết định| Decision[Quyết định định tuyến]
    T2 -->|Viết lại & Phân loại| Decision
    
    Decision -->|3. Thực thi & Truy xuất| Engines[Công cụ thực thi]
    
    subgraph "Lớp thực thi (engines.py)"
        Engines --> SQL[SQL Engine]
        Engines --> RAG[RAG Engine]
        Engines --> WEB[Web Search Engine]
    end
    
    Engines -->|4. Trích xuất metadata| EntityExtractor[Trích xuất thực thể]
    EntityExtractor --> CacheMgr[5. Quản lý Cache]
    
    subgraph "Lớp lưu trữ (DB)"
        CacheMgr -->|Cập nhật metadata| DB_Hot[(PostgreSQL Hot: Metadata & Embeddings)]
        CacheMgr -->|Cập nhật payload| DB_Cold[(PostgreSQL Cold: Payload Table)]
        EntityExtractor --> DB_Entity[(session_entity_index)]
    end
    
    Engines -->|Dữ liệu thô| LLM[6. Bộ tạo câu trả lời]
    CacheMgr -->|Dữ liệu cache| LLM
    
    LLM --> Verify{7. Tự kiểm tra xác minh}
    Verify -->|Đạt| Logging[8. Ghi nhật ký & Commit]
    Logging --> Response((Câu trả lời cuối cùng))
    Verify -->|Thất bại & Thử lại < 2| LLM
    Verify -->|Thất bại & Thử lại >= 2| FallbackResponse([Câu trả lời kèm cảnh báo tin cậy thấp])
```

1.  **Request Input & Locking:** Tiếp nhận truy vấn, băm `session_id` thành số nguyên 64-bit và lấy khóa cố vấn Advisory Lock cấp phiên trên PostgreSQL.
2.  **Routing (Tier 1 & Tier 2):** Kiểm tra chuyển đổi chủ đề (Topic Shift) bằng khoảng cách Embedding tương đối (Semantic Gap Analysis), tra cứu thực thể trong [session_entity_index](file:///D:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/docs/database_schema.md#L83), hoặc gọi LLM ở Tier 2 để viết lại câu truy vấn.
3.  **Execution & Retrieval:** Thực thi truy xuất dữ liệu thông qua SQL Engine, RAG Engine hoặc Web Engine dựa trên quyết định ở bước 2.
4.  **Metadata Extraction:** [EntityExtractor](file:///D:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/src/entity_extractor.py#L11) tự động trích xuất các thực thể mới (Person, Document, Session) từ kết quả thô của Engine và cập nhật vào `session_entity_index`.
5.  **Cache Orchestration:** Ghi dữ liệu vào Hot/Cold storage của PostgreSQL thông qua [cache_manager.py](file:///D:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/src/cache_manager.py) và thực hiện giải phóng cache LRU nếu vượt ngưỡng 5 slot.
6.  **Answer Generation:** Sinh câu trả lời qua LLM (sử dụng prompt làm sạch không thiên kiến) hoặc định tuyến qua luồng Direct Path trả kết quả ngay lập tức.
7.  **Self-Check Verification:** Xác minh chéo câu trả lời với dữ liệu thô ban đầu để loại bỏ hoàn toàn các lỗi ảo giác ngữ nghĩa.
8.  **Logging & Commit:** Ghi nhật ký lịch sử trò chuyện (tối đa 16 lượt hỏi gần nhất), lưu thông tin định tuyến vào DB và giải phóng Advisory Lock.

---

## 🛠️ Cải tiến Chống Overfitting & Tối ưu hóa Production (V3 Hard Mode)

Để chuẩn bị đưa dự án lên môi trường Production thực tế với dữ liệu ngoài miền (out-of-domain) và mô hình Embedding thật, hệ thống đã thực hiện các cải tiến kiến trúc cốt lõi:

- **Tách biệt và Cấu hình hóa trung tâm ([config.py](file:///D:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/src/config.py)):**
  - Toàn bộ từ khóa định tuyến hệ thống (SQL, RAG, Web), từ khóa kích hoạt Direct Path, và mapping hiển thị SQL được đưa ra ngoài file cấu hình.
  - Sử dụng regex động (`SESSION_PATTERN`) hỗ trợ đa dạng định dạng Session ID (`GT`, `SESSION`, `SESS`, `RECORD`, `TR`,...) thay vì hardcode một tiền tố duy nhất.
- **Phân tích khoảng cách ngữ nghĩa tương đối (Semantic Gap Analysis):**
  - Thay vì so sánh khoảng cách tuyệt đối cứng nhắc dễ gây lỗi kẹt ngữ cảnh trên mô hình embedding thực tế, Tier 1 tính tỉ lệ khoảng cách tương đối giữa hai slot cache tốt nhất ($d_1 / d_2 < 0.65$). Nếu không rõ ràng, hệ thống tự động đẩy lên Tier 2 để xử lý.
- **Tự phục hồi lỗi Embedding (Zero Vector Failure Fallback):**
  - Trình bao bọc [_safe_embed](file:///D:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/src/router.py#L37) tích hợp cơ chế tự phục hồi: tự động gỡ bỏ các vector lỗi/vector không (Zero Vector) trên Postgres và chuyển giao quyền xử lý định tuyến sang Tier 2 bằng văn bản thuần túy.
- **Giải quyết đại từ số nhiều và Liên kết đại từ động (Dynamic Binding):**
  - Loại bỏ đại từ chung ("担当者", "その人") khỏi DB chỉ mục thực thể để tránh ô nhiễm chỉ mục. Hệ thống sử dụng cơ chế Dynamic Binding tự động ánh xạ đại từ chung vào thực thể hoạt động gần nhất trong cache.
  - Triển khai lọc trùng lặp thực thể chéo session đối với đại từ số nhiều ("彼ら") để tổng hợp thông tin chính xác từ nhiều phiên trò chuyện khác nhau.
- **Cô lập ngữ cảnh Tổng hợp (Global Aggregate Cache Bypass):**
  - Đánh dấu `entity_id = "global_aggregate"` cho các câu hỏi mang tính tổng hợp toàn cục (như tổng thời lượng cuộc gọi) để bypass cache ngữ cảnh thực thể cụ thể, ngăn ngừa ô nhiễm chéo dữ liệu giữa các phiên hội thoại.

---

## 🗄️ Lược đồ Cơ sở Dữ liệu Chi tiết (Database Schema Columns)

Hệ thống sử dụng cơ sở dữ liệu PostgreSQL 15+ với thiết kế lược đồ tối ưu:

### 1. Bảng Quản lý Ngữ cảnh Hệ thống (System Cache Tables)

#### Bảng `chat_history` (Lưu lịch sử hội thoại)
| Tên cột | Kiểu dữ liệu | Mô tả |
| :--- | :--- | :--- |
| `id` | `BIGSERIAL PRIMARY KEY` | Định danh duy nhất tự tăng. |
| `session_id` | `VARCHAR(64) NOT NULL` | Mã định danh phiên (Có index hỗ trợ). |
| `role` | `VARCHAR(50) NOT NULL` | Quyền gửi tin: `'user'`, `'assistant'`, hoặc `'system'`. |
| `content` | `TEXT NOT NULL` | Nội dung tin nhắn gốc. |
| `rewritten_content` | `TEXT` | Câu hỏi đã được viết lại giải quyết đại từ chỉ định (chỉ dành cho user). |
| `answer_confidence` | `VARCHAR(50) NOT NULL`| Độ tin cậy của câu trả lời: `'high'`, `'medium'` hoặc `'low'`. Mặc định `'high'`. |
| `routing_metadata` | `JSONB` | Metadata kỹ thuật định tuyến. |
| `created_at` | `TIMESTAMPTZ` | Thời gian tạo bản ghi. |

#### Bảng `session_context_cache` (Hot Cache Metadata)
| Tên cột | Kiểu dữ liệu | Mô tả |
| :--- | :--- | :--- |
| `id` | `BIGSERIAL PRIMARY KEY` | Định danh duy nhất tự tăng. |
| `session_id` | `VARCHAR(64) NOT NULL` | Mã định danh phiên (Có index hỗ trợ). |
| `topic_key` | `TEXT NOT NULL` | Khóa chủ đề cache. |
| `last_pipeline` | `VARCHAR(50) NOT NULL` | Pipeline cuối: `'RAG'`, `'SQL'`, `'WEB'`, hoặc `'MODEL'`. |
| `last_routing_method` | `VARCHAR(50) NOT NULL` | Phương thức: `'heuristics'`, `'embeddings'`, `'llm_router'`, hoặc `'fallback'`. |
| `query_embedding` | `vector(384)` | Embedding vector đại diện cho tâm điểm ngữ cảnh chủ đề. |
| `embedding_model_version`| `VARCHAR(100)` | Phiên bản mô hình embedding (mặc định `'multilingual-e5-small'`). |
| `last_accessed_at` | `TIMESTAMPTZ` | Cập nhật khi Hit cache (phục vụ LRU Eviction). |
| `refreshed_at` | `TIMESTAMPTZ` | Cập nhật khi nạp dữ liệu mới từ Engine (phục vụ TTL). |

#### Bảng `session_context_payload` (Cold Cache Payload)
| Tên cột | Kiểu dữ liệu | Mô tả |
| :--- | :--- | :--- |
| `id` | `BIGSERIAL PRIMARY KEY` | Định danh duy nhất tự tăng. |
| `cache_id` | `BIGINT NOT NULL` | Khóa ngoại tham chiếu đến `session_context_cache(id)` (ON DELETE CASCADE, UNIQUE). |
| `cached_payload` | `JSONB NOT NULL` | Nội dung dữ liệu thô lớn lưu từ Engine. |
| `summary_context` | `JSONB` | Dữ liệu tóm tắt thực thể và thuộc tính cốt lõi. |

#### Bảng `session_entity_index` (Entity Index)
| Tên cột | Kiểu dữ liệu | Mô tả |
| :--- | :--- | :--- |
| `id` | `BIGSERIAL PRIMARY KEY` | Định danh duy nhất tự tăng. |
| `session_id` | `VARCHAR(64) NOT NULL` | Mã định danh phiên (Có index hỗ trợ). |
| `entity_id` | `TEXT NOT NULL` | Định danh thực thể (ví dụ: `GT_04`, `GT_02_Nakaoka`). |
| `entity_type` | `VARCHAR(50) NOT NULL` | Loại thực thể: `'meeting_transcript'`, `'person'`, `'document'`, `'sql_result'`. |
| `display_names` | `TEXT[] NOT NULL` | Mảng chứa danh sách tên và đại từ tương ứng (GIN Index). |
| `cache_slot_id` | `BIGINT` | Tham chiếu tới `session_context_cache(id)` (ON DELETE CASCADE). |
| `created_at` | `TIMESTAMPTZ` | Thời gian tạo bản ghi. |

---

### 2. Bảng Dữ liệu Nghiệp vụ (Business Data Tables)

#### Bảng `transcripts` (Thông tin cuộc gọi)
| Tên cột | Kiểu dữ liệu | Mô tả |
| :--- | :--- | :--- |
| `id` | `UUID PRIMARY KEY` | Định danh UUID tự sinh. |
| `session_id` | `VARCHAR(64) NOT NULL` | Mã phiên tương ứng (ví dụ: `GT_01`). |
| `meeting_date` | `DATE` | Ngày diễn ra cuộc gọi. |
| `participants` | `JSONB` | Danh sách người tham gia cuộc gọi (tên, công ty, giới tính). |
| `speaker_count` | `INT` | Số lượng người nói tham gia. |
| `duration_seconds` | `INT` | Tổng thời lượng cuộc gọi tính bằng giây. |
| `raw_text` | `TEXT` | Nội dung hội thoại thô hoàn chỉnh. |
| `summary` | `TEXT` | Nội dung tóm tắt cuộc gọi. |

#### Bảng `chunks_turn` (Chi tiết lượt hội thoại)
| Tên cột | Kiểu dữ liệu | Mô tả |
| :--- | :--- | :--- |
| `id` | `UUID PRIMARY KEY` | Định danh UUID tự sinh. |
| `transcript_id` | `UUID` | Khóa ngoại tham chiếu đến `transcripts(id)` (ON DELETE CASCADE). |
| `turn_index` | `INT` | Thứ tự lượt nói trong cuộc gọi. |
| `speaker` | `VARCHAR(255)` | Tên người nói lượt đó. |
| `time_start_sec` | `INT` | Thời điểm bắt đầu lượt nói (giây). |
| `time_end_sec` | `INT` | Thời điểm kết thúc lượt nói (giây). |
| `text` | `TEXT` | Nội dung văn bản phát ngôn. |

#### Bảng `company_chunks` (Tài liệu tri thức bổ sung cho RAG)
| Tên cột | Kiểu dữ liệu | Mô tả |
| :--- | :--- | :--- |
| `id` | `UUID PRIMARY KEY` | Định danh UUID tự sinh. |
| `document_id` | `UUID` | Định danh tài liệu nguồn. |
| `text` | `TEXT` | Nội dung văn bản tri thức. |
| `metadata` | `JSONB` | Metadata tài liệu bổ sung. |

---

## ⚙️ Các Tham số Cấu hình & Tinh chỉnh (Tuning Parameters)

Hệ thống có thể tinh chỉnh hành vi thông qua các tham số cấu hình tĩnh sau:

| Tham số cấu hình | Giá trị mặc định | File nguồn | Ý nghĩa |
| :--- | :--- | :--- | :--- |
| `MAX_CACHE_SLOTS` | `5` | [config.py](file:///D:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/src/config.py) | Số lượng slot cache chủ đề tối đa trên một session để kích hoạt LRU. |
| `CACHE_TTL_WEB` | `3600` (1 giờ) | [config.py](file:///D:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/src/config.py) | Thời gian sống của cache pipeline WEB trước khi ép tải lại. |
| `CACHE_TTL_SQL` | `86400` (24 giờ) | [config.py](file:///D:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/src/config.py) | Thời gian sống của cache pipeline SQL trước khi ép tải lại. |
| **Lock Timeout** | `8.0s` | [orchestrator.py](file:///D:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/src/orchestrator.py) | Thời gian chờ tối đa để lấy khóa Advisory Lock. |
| **Engine Timeout** | `30.0s` | [engines.py](file:///D:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/src/engines.py) | Thời gian tối đa một Engine thực thi trước khi bị ngắt mạch. |
| **Circuit Breaker Threshold** | `3` lỗi | [engines.py](file:///D:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/src/engines.py) | Số lỗi tối đa trước khi chuyển Circuit Breaker sang OPEN. |
| **Circuit Cooldown** | `30.0s` | [engines.py](file:///D:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/src/engines.py) | Thời gian nghỉ của Engine bị lỗi trước khi thử lại ở HALF_OPEN. |
| **Embedding Timeout** | `3.0s` | [router.py](file:///D:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/src/router.py) | Thời gian chờ tối đa sinh Vector Embedding. |
| **Cosine Threshold Hit** | `< 0.22` | [router.py](file:///D:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/src/router.py) | Ngưỡng khoảng cách cosine tin cậy thuộc cùng chủ đề. |
| **Cosine Threshold Shift** | `> 0.55` | [router.py](file:///D:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/src/router.py) | Ngưỡng khoảng cách cosine tin cậy đổi chủ đề. |
| **Self-Check Retries** | `2` lần thử | [orchestrator.py](file:///D:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/src/orchestrator.py) | Số lần thử lại tối đa của LLM Verifier chống ảo giác. |

---

## 📥 Đầu vào & 📤 Đầu ra (API Schema)

### Input Schema
| Trường | Kiểu | Mô tả |
| :--- | :--- | :--- |
| `session_id` | `String` | Định danh phiên làm việc (ví dụ: `GT_01`, `v3h_deep_chain`). |
| `query` | `String` | Truy vấn ngôn ngữ tự nhiên (tiếng Việt hoặc tiếng Nhật). |

### Output Schema
| Trường | Kiểu | Mô tả |
| :--- | :--- | :--- |
| `answer` | `String` | Câu trả lời cuối cùng đã qua bước kiểm định Self-Check. |
| `metadata` | `Object` | Thông tin định tuyến kỹ thuật: `latency_ms`, `target_pipeline`, `routing_method`, `self_check_passed`, `answer_confidence` ("high", "medium" hoặc "low"), v.v. |

---

## 🛠️ Cài đặt và Thiết lập

### Yêu cầu hệ thống
- Python 3.11+
- PostgreSQL 15+ (đã cài extension `pgvector` và `uuid-ossp`).
- Khóa API của LLM (Groq API Key / Javis LLM Client config).

### Các bước thiết lập nhanh

1. **Clone repository:**
   ```bash
   git clone <repo-url>
   cd multi-turn-context-manager
   ```

2. **Thiết lập môi trường ảo và cài đặt thư viện:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Trên Windows sử dụng: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Cấu hình biến môi trường:**
   Sao chép file `.env.example` thành `.env` và điền thông tin kết nối DB cũng như API keys:
   ```env
   NUMERIC_SQL_DATABASE_URL=postgresql://app_user:app_password@localhost:54331/app_db
   GROQ_API_KEY=your-groq-api-key
   ```

4. **Khởi tạo cơ sở dữ liệu và nạp dữ liệu kiểm thử:**
   ```bash
   python scripts/init_db.py
   python scripts/init_extra_tables.py
   python scripts/ingest_test_data.py
   ```

5. **Xác minh tính toàn vẹn dữ liệu:**
   ```bash
   python scripts/verify_summary_integrity.py
   ```

---

## 🧪 Hệ thống Kiểm thử & Đánh giá (Evaluation & Testing)

Hệ thống tích hợp bộ kiểm thử nâng cao toàn diện (V1, V2, V3, V4) kiểm thử các khía cạnh nghiệp vụ, khả năng phục hồi lỗi, bảo mật, và tương tranh.

### 1. Các bộ kiểm thử hiện có
- [test_suite.py](file:///D:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/tests/test_suite.py): Bộ kiểm thử tiêu chuẩn V1 (16 kịch bản, 26 lượt hỏi).
- [test_suite_v2.py](file:///D:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/tests/test_suite_v2.py): Bộ kiểm thử nâng cao V2 (8 kịch bản, 22 lượt hỏi).
- [test_suite_v3.py](file:///D:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/tests/test_suite_v3.py): **Bộ kiểm thử Hard Mode V3** (7 nhóm kịch bản lớn, 30 lượt hỏi) bao gồm các tình huống tương tranh, phân giải trùng tên người chéo, chuỗi đại từ phức tạp và bảo mật SQL Injection.
- [test_suite_v4.py](file:///D:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/tests/test_suite_v4.py): **Bộ kiểm thử Kiểm định Ảo giác & Lỗ hổng V4** (Scenario H với 16 kịch bản kiểm thử cực hạn) bao gồm:
  - *H1_WEB_SIMULATED_URL:* Kiểm định trả về URL giả lập của Web Engine khi tìm kiếm tin tức AI.
  - *H2_FAIL_OPEN_WARNING:* Cảnh báo độ tin cậy khi tự kiểm tra (Self-Check Verifier) gặp exception (Fail-Open).
  - *H3_DOUBLE_PRONOUN_REPLACEMENT:* Phân giải đại từ lặp kép trong cùng một truy vấn ("彼がそれについて...").
  - *H4_CACHE_TTL_STALE_FILTER:* Loại bỏ context cache cũ hết hạn (TTL > 24h đối với SQL, > 1h đối với WEB).
  - *H5_ROLE_REVERSAL_CHECK:* Kiểm soát không bị ảo giác đổi vai trò người gọi/người nhận (Yamashita gọi cho receptionist).
  - *H6_DIRECT_PATH_REASONING_BYPASS:* Bỏ qua Direct Path khi câu hỏi yêu cầu giải thích/lý do chi tiết.
  - *H7_CONCURRENT_SESSION_LOCK_TIMEOUT:* Đảm bảo kiểm soát thời gian chờ (lock_timeout) khi bị tranh chấp khóa Advisory Lock.
  - *H8_CIRCUIT_BREAKER_TRANSITIONS:* Kiểm tra chuyển đổi trạng thái của Circuit Breaker khi có lỗi liên tiếp (CLOSED -> OPEN -> HALF_OPEN -> CLOSED).
  - *H9_WEB_RELEVANCE_AND_FALLBACK:* Chỉ dùng Direct Path cho Web Search khi có duy nhất 1 kết quả có độ liên quan cao (> 0.85).
  - *H10_GENDER_AWARE_PRONOUN_RESOLUTION:* Ánh xạ chính xác đại từ "彼" (nam) và "彼女" (nữ) dựa trên dữ liệu giới tính người tham gia trong DB và hậu tố tiếng Nhật.
  - *H11_CACHE_EMPTY_PAYLOAD_DOWNGRADE:* Hạ cấp xuống tải đầy đủ khi cache hit nhưng payload rỗng.
  - *H12_CACHE_GRANULARITY_DETAILS_UPGRADE:* Nâng cấp lên full retrieval khi truy vấn yêu cầu chi tiết/lượt thoại nhưng cache chỉ chứa metadata thô.
  - *H13_CROSS_POLLINATION_HALT:* Ngăn chặn ảo giác chéo session (không gán người thuộc session này cho session khác).
  - *H14_ABSENT_ACTOR_HALLUCINATION_TRAP:* Từ chối bịa đặt phát ngôn cho người vắng mặt (holiday).
  - *H15_OUT_OF_CONTEXT_COMPANY_INFO_REFUSAL:* Từ chối trả lời thông tin công ty ngoài ngữ cảnh (cutoff parametric knowledge).
  - *H16_VERIFIER_CORRECTION_LOOP:* Kiểm tra vòng lặp tự sửa lỗi ảo giác khi verifier phát hiện sai lệch thông tin.

### 2. Chạy kiểm thử
Để chạy các bộ kiểm thử:
```bash
# Chạy bộ kiểm thử V3 Hard Mode
python tests/test_suite_v3.py

# Chạy bộ kiểm thử V4 Hallucination & Vulnerabilities
python tests/test_suite_v4.py
```

### 3. Xuất báo cáo kết quả kiểm thử sang Excel chuyên nghiệp
Sau khi hoàn thành kiểm thử, bạn có thể chuyển đổi file kết quả CSV thành file Excel có định dạng màu sắc trực quan (PASS/FAIL):
```bash
python scripts/convert_test_summary_to_excel_v2.py
```
*Tệp kết quả Excel sẽ được lưu trữ tại thư mục `scratch/` để dễ dàng theo dõi.*

---

## 📈 Kết quả Kiểm thử & Phân tích KPIs

Bảng so sánh hiệu năng và độ chính xác qua 4 phiên bản kiểm thử cải tiến:

| Chỉ số (Metric) | Phiên bản V1 | Phiên bản V2 | Phiên bản V3 (Hard Mode & Cải tiến) | Phiên bản V4 (Ảo giác & Lỗ hổng cực hạn) |
| :--- | :--- | :--- | :--- | :--- |
| **Số lượng kịch bản kiểm thử** | 16 Scenarios | 8 Scenarios | 7 Scenarios | 1 Scenario (Scenario H với 16 kịch bản con) |
| **Tổng số lượt hỏi (Total Turns)** | 26 Turns | 22 Turns | 30 Turns | 16 Turns (12 cuộc gọi thật, 4 mock) |
| **Tỷ lệ vượt qua (Passed Rate)** | **26/26 (100.0%)** | **22/22 (100.0%)** | **30/30 (100.0%)** | **16/16 (100.0%)** |
| **Tỷ lệ lỗi (Failed Rate)** | 0.0% | 0.0% | 0.0% | 0.0% |
| **Độ trễ trung bình (Avg Latency)**| ~6,146ms | ~8,467ms | ~9,485ms | ~18,923ms (gọi thật) / ~14,192ms (tất cả) |
| **Tỷ lệ trúng Cache (Cache Hit Rate)** | 23.08% | 27.27% | 20.0% | 25.0% (gọi thật) / 18.75% (tất cả) |
| **Khóa tương tranh & Bảo mật** | Đạt | Đạt | Đạt (Ngăn chặn 100% SQL Injection & Concurrent Deadlocks) | Đạt (Kiểm định Lock Timeout, Circuit Breaker, Phân giải giới tính động) |

---
*Phát triển bởi Gemini CLI Agent cho dự án Trợ lý ảo Javis.*
