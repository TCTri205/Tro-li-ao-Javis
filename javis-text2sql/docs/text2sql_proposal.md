# ĐỀ XUẤT THIẾT KẾ MODULE TEXT-TO-SQL
## Trợ lý ảo Javis — Phân hệ Đồng bộ Dữ liệu và Truy vấn Có cấu trúc

Tài liệu này trình bày thiết kế chi tiết và hoàn chỉnh cho **module Text-to-SQL** độc lập thuộc hệ thống Trợ lý ảo Javis.
Trong kiến trúc tổng thể, Text-to-SQL hoạt động như một **công cụ (Tool)** được gọi bởi tác nhân điều phối (Routing Node), chuyên trách việc xử lý các câu hỏi định lượng và số liệu từ người dùng dựa trên cơ sở dữ liệu quan hệ PostgreSQL được đồng bộ hóa.

---

## 1. Kiến trúc Tổng quan Module

Trong hệ thống Javis, Text-to-SQL không phải là hệ thống truy vấn chính, mà đóng vai trò là một **Tool** được kích hoạt có chọn lọc. Đầu vào của hệ thống là câu hỏi của người dùng, được đi qua một **Routing Node** để phân loại luồng xử lý:

```
                  [CÂU HỎI CỦA USER]
                          │
                          ▼
                  ┌───────────────┐
                  │ Routing Node  │
                  └───────┬───────┘
                          │
            ┌─────────────┴─────────────┐
            │ (Câu hỏi thường/Ngữ cảnh)  │ (Câu hỏi số liệu/Định lượng)
            ▼                           ▼
    ┌───────────────┐           ┌───────────────┐
    │  Vector RAG   │           │   Text2SQL    │
    │  (Semantic)   │           │    (Tool)     │
    └───────┬───────┘           └───────┬───────┘
            │                           │
            └─────────────┬─────────────┘
                          │
                          ▼
                     [RESPONSE]
```

### Quy trình tổng quát:
1. **Phân hệ Nạp dữ liệu (ETL / Text-to-SQL DB):** Phân tách văn bản cuộc họp thô (tiếng Nhật/Việt) thành các lượt thoại (turns) và đoạn (passages), sau đó LLM trích xuất tự động các metadata có cấu trúc để lưu vào PostgreSQL.
2. **Routing Node:** Phân tích câu hỏi của người dùng. Nếu câu hỏi yêu cầu tính toán, thống kê, đếm hoặc lọc thông tin có cấu trúc (ví dụ: ngày tháng, số tiền, cam kết), hệ thống sẽ gọi **Text2SQL Tool**. Ngược lại, nếu là câu hỏi tìm hiểu ngữ cảnh, ý kiến hoặc tóm tắt, hệ thống sẽ đi qua **Vector RAG**.
3. **Phân hệ Truy vấn (NL-to-SQL Tool):** Biên dịch câu hỏi thành truy vấn SQL chuẩn xác, thực thi trên các PostgreSQL Semantic Views và trả về kết quả số liệu chính xác.

---

## 2. PHẦN A: Phân hệ Nạp dữ liệu (ETL / Text-to-SQL DB)

Mục tiêu của phân hệ này là chuẩn hóa, làm sạch và lưu trữ có cấu trúc các cuộc thảo luận phi cấu trúc của cuộc họp để phục vụ cho các thuật toán truy vấn định lượng sau này.

### 2.1. Thiết kế Lược đồ Cơ sở Dữ liệu Vật lý (Physical Schema)

Chúng ta sử dụng cơ sở dữ liệu **PostgreSQL** để lưu trữ các tầng thông tin cuộc họp (Turn -> Passage -> Meeting). Các thuộc tính mảng và đối tượng được tổ chức dưới dạng cột `JSONB` kết hợp với chỉ mục GIN để tối ưu hóa hiệu năng và tính linh hoạt.

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 1. Bảng lưu thông tin cuộc họp tổng quan
CREATE TABLE meetings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title TEXT NOT NULL,
    meeting_date DATE NOT NULL,
    speaker_count INT NOT NULL,
    duration_seconds INT NOT NULL,
    summary TEXT,
    topics JSONB DEFAULT '[]'::jsonb, -- Danh sách chủ đề tổng quan toàn cuộc họp
    source_language VARCHAR(10) NOT NULL DEFAULT 'vi', -- Ngôn ngữ cuộc họp: 'vi' | 'ja' | 'mixed'
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 2. Bảng lưu các Passage (mỗi passage chứa 8-10 turns liên tiếp)
CREATE TABLE passages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    passage_index INT NOT NULL,
    content TEXT NOT NULL, -- Nội dung thô chứa toàn bộ lượt nói trong passage
    
    -- Nhóm 1: Nội dung & Chủ đề
    topics JSONB DEFAULT '[]'::jsonb, -- Ví dụ: ["chi phí điện", "budget Q3"]
    entities JSONB DEFAULT '[]'::jsonb, -- Ví dụ: ["EVN", "500 triệu"]
    keywords JSONB DEFAULT '[]'::jsonb, -- Từ khóa domain-specific
    
    -- Nhóm 2: Loại phát ngôn & Action items
    turn_types TEXT[] NOT NULL DEFAULT '{}', -- Mảng chứa các loại phát ngôn: decision, question, proposal, complaint, update, small_talk
    has_action_item BOOLEAN NOT NULL DEFAULT FALSE,
    action_item_text TEXT,
    has_question BOOLEAN NOT NULL DEFAULT FALSE,
    question_text TEXT, -- Chi tiết câu hỏi chưa có câu trả lời (được trích xuất riêng)
    
    -- Nhóm 3: Con số & Mốc thời gian
    amounts JSONB DEFAULT '[]'::jsonb, -- Ví dụ: [{"value": 500, "unit": "triệu", "currency": "VND", "context": "budget"}]
    dates_mentioned JSONB DEFAULT '[]'::jsonb, -- Mảng chứa thông tin ngày tháng: [{"raw_text": "thứ Sáu tuần sau", "resolved_date": "2026-06-05", "confidence": 0.9}]
    
    -- Nhóm 4: Cảm xúc & Mức độ quan trọng
    sentiment VARCHAR(20) NOT NULL, -- positive, negative, neutral
    importance_score INT NOT NULL CHECK (importance_score BETWEEN 1 AND 5),
    enrichment_status VARCHAR(20) NOT NULL DEFAULT 'success', -- Trạng thái trích xuất: 'success' | 'llm_failed'
    
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_passage_per_meeting UNIQUE (meeting_id, passage_index)
);

-- 3. Bảng lưu chi tiết từng lượt nói (Turn) trong Passage
CREATE TABLE turns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    passage_id UUID NOT NULL REFERENCES passages(id) ON DELETE CASCADE,
    meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    turn_index INT NOT NULL,
    speaker TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_turn_per_passage UNIQUE (passage_id, turn_index)
);

-- 4. Bảng ánh xạ thực thể (Entity/Value Mapping Layer)
CREATE TABLE entity_aliases (
    id SERIAL PRIMARY KEY,
    canonical_name TEXT NOT NULL,       -- Tên chuẩn hóa: "EVN"
    alias TEXT NOT NULL,                -- Dạng khác: "Tập đoàn điện lực", "電力会社"
    language CHAR(2) NOT NULL,          -- 'vi', 'ja', 'en'
    entity_type VARCHAR(50),            -- 'organization', 'person', 'product'
    UNIQUE (alias, language)
);

-- 5. Bảng lưu các cam kết từ cuộc họp (Đã chuẩn hóa từ mảng JSONB trong passages)
CREATE TABLE commitments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    passage_id UUID NOT NULL REFERENCES passages(id) ON DELETE CASCADE,
    meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    person TEXT NOT NULL,
    action TEXT NOT NULL,
    deadline TEXT,
    deadline_date DATE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending', -- 'pending' | 'done' | 'cancelled'
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- TỐI ƯU HÓA HIỆU NĂNG BẰNG CHỈ MỤC (INDEXES)
CREATE INDEX idx_passages_meeting_id ON passages (meeting_id);
CREATE INDEX idx_turns_passage_id ON turns (passage_id);
CREATE INDEX idx_turns_meeting_id ON turns (meeting_id);
CREATE INDEX idx_meetings_meeting_date ON meetings (meeting_date);
CREATE INDEX idx_passages_sentiment ON passages (sentiment);
CREATE INDEX idx_passages_importance ON passages (importance_score);
CREATE INDEX idx_commitments_passage_id ON commitments (passage_id);
CREATE INDEX idx_commitments_meeting_id ON commitments (meeting_id);
CREATE INDEX idx_commitments_person ON commitments (person);
CREATE INDEX idx_commitments_status ON commitments (status);

-- Chỉ mục GIN cho các cột JSONB và Mảng
CREATE INDEX idx_passages_topics ON passages USING gin (topics);
CREATE INDEX idx_passages_entities ON passages USING gin (entities);
CREATE INDEX idx_passages_amounts ON passages USING gin (amounts);
CREATE INDEX idx_passages_turn_types ON passages USING gin (turn_types);

-- Chỉ mục GIN trigram cho bảng entity_aliases để tìm kiếm mờ (fuzzy search)
CREATE INDEX idx_entity_aliases_trgm ON entity_aliases USING gin (alias gin_trgm_ops);
```

### 2.2. Logic Chunker Phân tầng Dữ liệu (Rule-based)

Để giảm thiểu chi phí tính toán và độ phức tạp khi dựng môi trường, thay vì sử dụng mô hình AI Semantic Chunker ở Phase 1, hệ thống áp dụng **Rule-based Chunker** kết hợp ngắt đoạn theo thời gian:
1. **Tách Turn:** Trích xuất lượt nói dựa trên các regex thông dụng hỗ trợ cấu trúc `[Speaker]: [Content]` hoặc định dạng thời gian `[HH:MM:SS] Speaker: Content`.
2. **Rule-based Passage Chunker:**
   - Tự động gộp nhóm từ **8 đến 10 lượt thoại liên tiếp** thành một đoạn (passage) để đảm bảo ngữ cảnh thảo luận không bị rời rạc.
   - Hoặc ngắt đoạn sớm hơn nếu khoảng lặng giữa 2 lượt thoại kế tiếp vượt quá **3 phút** (180 giây).

### 2.3. Thiết kế LLM Metadata Enrichment (Trích xuất Thông tin)

Sử dụng tính năng **LLM Structured Outputs** của mô hình AI để xuất ra dữ liệu JSON chính xác khớp với schema.

#### Định nghĩa Schema Pydantic cho Metadata Extraction:

```python
from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Literal
from datetime import date
from uuid import uuid4

class AmountInfo(BaseModel):
    value: float = Field(description="Giá trị số của khoản tiền")
    unit: str = Field(description="Đơn vị tiền tệ (ví dụ: triệu, tỷ, man, yên)")
    currency: str = Field(description="Ký hiệu tiền tệ chuẩn hóa (VND, JPY, USD)")
    context: str = Field(description="Ngữ cảnh của con số tài chính này")

class DateMention(BaseModel):
    raw_text: str = Field(description="Ngày tháng dạng text thô: thứ Sáu, tuần sau, cuối tháng 7")
    resolved_date: Optional[date] = Field(description="Ngày tháng quy đổi sang định dạng YYYY-MM-DD (ISO format) nếu xác định được, ngược lại là null")
    confidence: float = Field(description="Độ tin cậy của việc quy đổi ngày tháng (từ 0.0 đến 1.0)")

class CommitmentInfo(BaseModel):
    # commitment_id bắt buộc có để PATCH API có thể định vị phần tử trong mảng JSONB của DB
    commitment_id: str = Field(
        default_factory=lambda: str(uuid4()), 
        description="ID duy nhất cho cam kết dưới dạng UUID"
    )
    person: str = Field(description="Tên người cam kết thực hiện công việc")
    action: str = Field(description="Nội dung công việc cam kết thực hiện")
    deadline: str = Field(description="Thời hạn thực hiện công việc dạng thô")
    deadline_date: Optional[date] = Field(description="Quy đổi deadline sang ngày cụ thể định dạng YYYY-MM-DD nếu xác định được, ngược lại là null")
    status: Literal["pending", "done", "cancelled"] = Field(default="pending", description="Trạng thái thực hiện cam kết")

class PassageEnrichmentSchema(BaseModel):
    topics: List[str] = Field(description="Danh sách các chủ đề chính thảo luận trong đoạn")
    entities: List[str] = Field(description="Các thực thể nổi bật: tên riêng, địa điểm, công nghệ")
    keywords: List[str] = Field(description="Từ khóa chuyên biệt để tìm kiếm")
    turn_types: List[Literal["decision", "question", "proposal", "complaint", "update", "small_talk"]] = Field(description="Danh sách các loại phát ngôn xuất hiện trong đoạn")
    has_action_item: bool = Field(description="Đoạn này có giao việc hay không")
    action_item_text: Optional[str] = Field(description="Mô tả hành động cần làm nếu có")
    has_question: bool = Field(description="Đoạn này có chứa câu hỏi chưa có câu trả lời hay không")
    question_text: Optional[str] = Field(description="Chi tiết câu hỏi chưa có câu trả lời được thảo luận")
    amounts: List[AmountInfo] = Field(description="Danh sách các con số tài chính được nhắc đến")
    dates_mentioned: List[DateMention] = Field(description="Các mốc ngày tháng đề cập trong hội thoại")
    commitments: List[CommitmentInfo] = Field(description="Các cam kết/giao hẹn nhiệm vụ trong đoạn")
    sentiment: Literal["positive", "negative", "neutral"]
    importance_score: int = Field(description="Đánh giá độ quan trọng từ 1 (thấp nhất) đến 5 (cao nhất)", ge=1, le=5)

    @model_validator(mode='after')
    def check_metadata_consistency(self):
        # Đảm bảo tính nhất quán giữa cờ báo hiệu và trường văn bản chi tiết
        if self.has_action_item and not self.action_item_text:
            raise ValueError("action_item_text phải có giá trị khi has_action_item=True")
        if self.has_question and not self.question_text:
            raise ValueError("question_text phải có giá trị khi has_question=True")
        return self
```
> [!IMPORTANT]
> `enrichment_status` là cột DB để theo dõi tiến trình nạp (thành công hay lỗi LLM). Nó **không nằm trong Pydantic schema** để tránh lỗi `AttributeError` khi LLM sinh dữ liệu. Trạng thái này sẽ được gán trực tiếp ở tầng Data Loader trước khi thực hiện câu lệnh SQL INSERT.

### 2.4. Quy trình Tải Dữ liệu (SQL Data Loader)

```python
# etl/loader.py
import asyncio
import json
import logging
from datetime import date
from uuid import uuid4

# Giới hạn số lượng request LLM đồng thời tránh bị rate limit
semaphore = asyncio.Semaphore(10)

async def enrich_passage(passage_content: str, passage_index: int, meeting_date: date, llm_client) -> tuple[dict, str]:
    """
    Trả về dữ liệu đã trích xuất (schema dict) và trạng thái enrichment_status
    """
    system_prompt = f"You are an expert NLP extractor. Reference date: {meeting_date.isoformat()}."
    
    for attempt in range(3):
        try:
            async with semaphore:
                # LLM trả về object khớp với PassageEnrichmentSchema
                result_obj = await llm_client.structured_output(
                    system=system_prompt,
                    user=passage_content,
                    schema=PassageEnrichmentSchema
                )
                return result_obj.model_dump(), "success"
        except Exception as e:
            if attempt == 2:
                logging.error(f"Passage {passage_index} enrichment failed: {e}")
                # Trả về schema trống dạng fallback
                return get_empty_schema_dict(passage_content), "llm_failed"
            await asyncio.sleep(2 ** attempt)

async def load_meeting(raw_transcript: str, meeting_meta: dict, db_pool, llm_client):
    turns = split_turns(raw_transcript)
    # Chia nhóm theo Rule-based (cắt mỗi 10 turns)
    passage_groups = chunk_turns_into_passages(turns, max_turns=10)
    
    # Enrichment song song với semaphore control
    enrich_tasks = [
        enrich_passage(
            passage_content="\n".join(f"{t.speaker}: {t.content}" for t in group),
            passage_index=idx,
            meeting_date=meeting_meta["meeting_date"],
            llm_client=llm_client
        )
        for idx, group in enumerate(passage_groups)
    ]
    enrichment_results = await asyncio.gather(*enrich_tasks)

    # Thực hiện lưu DB trong transaction
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            meeting_id = await conn.fetchval(
                """INSERT INTO meetings (title, meeting_date, speaker_count, duration_seconds, summary, source_language) 
                   VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
                meeting_meta["title"], meeting_meta["meeting_date"], meeting_meta["speaker_count"],
                meeting_meta["duration_seconds"], meeting_meta["summary"], meeting_meta["source_language"]
            )
            
            for idx, (group, (schema_data, e_status)) in enumerate(zip(passage_groups, enrichment_results)):
                # Insert passage - gán status ở đây, không gán trong Pydantic object
                passage_id = await conn.fetchval(
                    """INSERT INTO passages 
                       (meeting_id, passage_index, content, topics, entities,
                        turn_types, has_action_item, action_item_text,
                        amounts, dates_mentioned,
                        sentiment, importance_score, enrichment_status)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13) RETURNING id""",
                    meeting_id, idx,
                    "\n".join(f"{t.speaker}: {t.content}" for t in group),
                    json.dumps(schema_data["topics"]),
                    json.dumps(schema_data["entities"]),
                    schema_data["turn_types"],
                    schema_data["has_action_item"],
                    schema_data["action_item_text"],
                    json.dumps(schema_data["amounts"]),
                    json.dumps(schema_data["dates_mentioned"]),
                    schema_data["sentiment"],
                    schema_data["importance_score"],
                    e_status  # Gán trạng thái thành công hoặc lỗi LLM
                )
                
                # Insert commitments liên quan (Đã chuẩn hóa)
                if schema_data["commitments"]:
                    await conn.executemany(
                        """INSERT INTO commitments 
                           (passage_id, meeting_id, person, action, deadline, deadline_date, status)
                           VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                        [(passage_id, meeting_id, c["person"], c["action"], c["deadline"], c["deadline_date"], c["status"]) 
                         for c in schema_data["commitments"]]
                    )
                
                # Insert turns liên quan
                await conn.executemany(
                    "INSERT INTO turns (passage_id, meeting_id, turn_index, speaker, content, timestamp) VALUES ($1,$2,$3,$4,$5,$6)",
                    [(passage_id, meeting_id, t.turn_index, t.speaker, t.content, t.timestamp) for t in group]
                )
```

---

## 3. PHẦN B: Phân hệ Truy vấn (NL-to-SQL Query)

Khi dữ liệu đã được cấu trúc hóa, phân hệ truy vấn sẽ dịch câu hỏi tự nhiên thành SQL và thực thi trên các View phẳng.

### 3.1. Thiết kế Semantic Layer (PostgreSQL Views)

Hệ thống sử dụng **8 Views** phẳng hóa dữ liệu vật lý để LLM không phải làm việc với các câu lệnh JSONB phức tạp của Postgres:

```sql
-- 1. View Chủ đề & Thực thể
CREATE VIEW v_topics AS
SELECT
    m.id AS meeting_id, m.title AS meeting_title, m.meeting_date, p.id AS passage_id,
    t.value::text AS topic, 'topic' AS source_type
FROM meetings m
JOIN passages p ON p.meeting_id = m.id
CROSS JOIN LATERAL jsonb_array_elements_text(p.topics) AS t
UNION ALL
SELECT
    m.id, m.title, m.meeting_date, p.id,
    e.value::text AS topic, 'entity' AS source_type
FROM meetings m
JOIN passages p ON p.meeting_id = m.id
CROSS JOIN LATERAL jsonb_array_elements_text(p.entities) AS e;

-- 2. View Cam kết (Được điều chỉnh từ table commitments đã chuẩn hóa)
CREATE VIEW v_commitments AS
SELECT
    m.id AS meeting_id, 
    m.title AS meeting_title, 
    m.meeting_date, 
    c.passage_id,
    c.id AS commitment_id,
    c.person,
    c.action,
    c.deadline,
    c.deadline_date,
    c.status
FROM meetings m
JOIN commitments c ON c.meeting_id = m.id;

-- 3. View Số tiền/Ngân sách
CREATE VIEW v_amounts AS
SELECT
    m.id AS meeting_id, m.title AS meeting_title, m.meeting_date, p.id AS passage_id,
    (a.value->>'value')::numeric AS amount_value,
    a.value->>'unit' AS amount_unit,
    a.value->>'currency' AS amount_currency,
    a.value->>'context' AS amount_context
FROM meetings m
JOIN passages p ON p.meeting_id = m.id
CROSS JOIN LATERAL jsonb_array_elements(p.amounts) AS a;

-- 4. View Hạng mục Hành động (Action items)
CREATE VIEW v_action_items AS
SELECT
    m.id AS meeting_id, m.title AS meeting_title, m.meeting_date, p.id AS passage_id,
    p.action_item_text, p.importance_score
FROM meetings m
JOIN passages p ON p.meeting_id = m.id
WHERE p.has_action_item = true;

-- 5. View Câu hỏi chưa được trả lời
CREATE VIEW v_open_questions AS
SELECT
    m.id AS meeting_id, m.title AS meeting_title, m.meeting_date, p.id AS passage_id,
    p.question_text, p.importance_score
FROM meetings m
JOIN passages p ON p.meeting_id = m.id
WHERE p.has_question = true;

-- 6. View Phát ngôn Tổng hợp
CREATE VIEW v_statements AS
SELECT
    m.id AS meeting_id, m.title AS meeting_title, m.meeting_date, p.id AS passage_id,
    p.turn_types, p.has_action_item, p.has_question, p.sentiment, p.importance_score, p.content
FROM meetings m
JOIN passages p ON p.meeting_id = m.id;

-- 7. View Mốc thời gian nhắc tới
CREATE VIEW v_dates AS
SELECT
    m.id AS meeting_id, m.title AS meeting_title, m.meeting_date, p.id AS passage_id,
    d.value->>'raw_text' AS date_raw_text,
    (d.value->>'resolved_date')::date AS date_resolved,
    (d.value->>'confidence')::numeric AS confidence
FROM meetings m
JOIN passages p ON p.meeting_id = m.id
CROSS JOIN LATERAL jsonb_array_elements(p.dates_mentioned) AS d;

-- 8. View Phân tích Phát ngôn theo Người nói
CREATE VIEW v_speaker_turns AS
SELECT
    m.id AS meeting_id, m.title AS meeting_title, m.meeting_date,
    t.speaker,
    t.content AS turn_content,
    t.timestamp,
    p.turn_types, p.sentiment, p.importance_score
FROM meetings m
JOIN passages p ON p.meeting_id = m.id
JOIN turns t ON t.passage_id = p.id;
```

---

### 3.2. Cấu trúc và Thiết kế của Routing Node

Để tối ưu hóa chi phí LLM và đảm bảo UX tốt nhất, hệ thống thiết kế **Routing Node** đóng vai trò điều phối ngay tại điểm tiếp nhận yêu cầu. Node này phân tích xem câu hỏi có chứa ý định cần tính toán/dẫn xuất số liệu để kích hoạt Text2SQL, hoặc gửi sang luồng Vector RAG cho câu hỏi định tính.

```python
from typing import Literal, Optional, List
from pydantic import BaseModel, Field

class RoutingDecision(BaseModel):
    route: Literal["sql", "rag", "hybrid"] = Field(
        description="Định tuyến xử lý: 'sql' cho số liệu, 'rag' cho ngữ cảnh/tóm tắt, hoặc 'hybrid' cho cả hai."
    )
    confidence: float = Field(description="Độ tin cậy của phân loại (0.0 đến 1.0)")
    sql_intent: Optional[Literal["aggregate", "filter", "list", "status_check"]] = Field(
        default=None, description="Loại ý định SQL nếu có"
    )
    requires_numeric: bool = Field(description="Yêu cầu câu trả lời có số liệu chính xác hay không")

# Ý định thuộc luồng SQL
SQL_INTENTS = {
    "aggregate":     ["tổng", "sum", "count", "đếm", "bao nhiêu"],
    "filter":        ["liệt kê", "list all", "tất cả những"],  
    "status_check":  ["pending", "done", "chưa xong", "hoàn thành chưa"],
    "date_filter":   ["tuần này", "tháng trước", "deadline", "今週", "先月"],
    "commitment":    ["cam kết", "giao việc", "action item", "約束"],
    "amount":        ["ngân sách", "chi phí", "số tiền", "予算"],
}

# Ý định thuộc luồng RAG
RAG_INTENTS = {
    "summary":       ["cuộc họp nói về gì", "tóm tắt", "summary"],
    "opinion":       ["ai nghĩ gì", "ý kiến của", "attitude"],
    "context":       ["tại sao", "why", "nguyên nhân"],
}

# Logic phân loại nhanh bằng heuristic/regex kết hợp LLM ở giai đoạn MVP
def route_question(question: str) -> Literal["sql", "rag"]:
    # Dấu hiệu cần SQL: tổng, đếm, liệt kê, deadline, ai đã làm gì, ngân sách...
    SQL_SIGNALS = [
        "tổng", "bao nhiêu", "liệt kê", "đếm", "tất cả", "kết quả", "thống kê",
        "deadline", "còn pending", "cam kết", "action item", "nhiệm vụ",
        "ngân sách", "chi phí", "số tiền", "tiền", "ngày", "bao giờ",
        # Tiếng Nhật
        "いくつ", "合計", "リスト", "期限", "タスク", "予算", "金額", "日付"
    ]
    question_lower = question.lower()
    if any(sig in question_lower for sig in SQL_SIGNALS):
        return "sql"
    return "rag"
```

#### Ví dụ phân biệt luồng xử lý (Edge Cases):
* *"Bình đã nói gì về ngân sách?"* -> **RAG** (Hỏi về ý kiến, quan điểm, không cần tính toán số học).
* *"Tổng ngân sách Bình cam kết là bao nhiêu?"* -> **SQL** (Cần cộng dồn cột `amount_value` chính xác).
* *"Cuộc họp quyết định gì về ngân sách điện và con số cụ thể là bao nhiêu?"* -> **Hybrid** (Kết hợp context của RAG và SQL để tính số tiền).

---

### 3.3. Quy trình NL-to-SQL Pipeline (Tối giản - Linear Flow)

Ở các giai đoạn đầu, hệ thống **không sử dụng LangGraph** để tránh phức tạp hóa kiến trúc. Text2SQL đóng vai trò là một **Tool** tuyến tính (Linear Pipeline) với cơ chế tự động sửa lỗi (Refiner) đơn giản chạy lại tối đa 1 lần.

```python
# query/pipeline.py
import re
from typing import Optional

def map_entities(question: str, db_conn) -> dict:
    """Sử dụng ILIKE đơn giản trên bảng entity_aliases ở Phase 1"""
    # Trích xuất các danh từ riêng hoặc thực thể tiềm năng và so khớp
    # Trả về dictionary dạng: {"Tập đoàn điện lực": "EVN"}
    ...

def resolve_temporal(question: str) -> Optional[dict]:
    """[ĐÃ BỎ] Quy đổi thời gian ở Python backend bằng Regex.
    Ở Phase 1, việc giải quyết các mốc thời gian tương đối được đẩy hoàn toàn cho LLM
    khi sinh SQL thông qua tham số Today's reference date truyền vào System Prompt."""
    return None

async def generate_sql(question: str, entities: dict, time_range: Optional[dict], llm_client) -> str:
    """Sinh SQL bằng LLM với 15 ví dụ mẫu (Few-shot) hardcode sẵn trong prompt"""
    few_shot_examples = """
Question: Anh Bình có cam kết gì chưa hoàn thành?
SQL: SELECT person, action, deadline FROM v_commitments WHERE person ILIKE '%Bình%' AND status = 'pending';

Question: Chi phí điện trong các cuộc họp tháng này là bao nhiêu?
SQL: SELECT SUM(amount_value) FROM v_amounts WHERE amount_context ILIKE '%điện%' AND meeting_date >= '2026-05-01';
"""
    system_prompt = f"""You are an expert SQL generator. Write PostgreSQL query to answer the user question.
Only query from allowed views: v_topics, v_commitments, v_amounts, v_action_items, v_open_questions, v_statements, v_dates, v_speaker_turns.
Today's reference date: 2026-05-26.
Few-shot examples:
{few_shot_examples}
"""
    sql = await llm_client.generate(system=system_prompt, user=question)
    return clean_sql_markdown(sql)

def validate_sql(sql: str) -> tuple[bool, str]:
    """Kiểm tra an toàn SQL qua thư viện sqlglot"""
    import sqlglot
    # 1. Chặn các từ khóa cấm thay đổi dữ liệu
    forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE"]
    if any(f in sql.upper() for f in forbidden):
        return False, "Chứa từ khóa cấm ghi dữ liệu"
    
    # 2. Parse cú pháp và kiểm tra tên bảng
    try:
        parsed = sqlglot.parse_one(sql, dialect="postgres")
        tables = [t.name for t in parsed.find_all(sqlglot.expressions.Table)]
        # Chỉ cho phép query trên views bắt đầu bằng v_
        non_views = [t for t in tables if not t.startswith("v_")]
        if non_views:
            return False, f"Chỉ được truy cập view phẳng, không được truy cập bảng: {non_views}"
        return True, ""
    except Exception as e:
        return False, f"Lỗi cú pháp SQL: {str(e)}"

async def text2sql_pipeline(question: str, db_pool, llm_client) -> dict:
    # Bước 1: Mapping thực thể
    entities = map_entities(question, db_pool)
    
    # Bước 2: LLM sinh SQL (nhận Today's reference date trong prompt để tự giải quyết thời gian tương đối)
    sql = await generate_sql(question, entities, None, llm_client)
    
    # Bước 3: Kiểm tra an toàn SQL
    is_safe, error_msg = validate_sql(sql)
    if not is_safe:
        return {"success": False, "error": f"Security validation failed: {error_msg}", "sql": sql}
        
    # Bước 4: Thực thi trên DB (Read-Only connection pool)
    async with db_pool.acquire() as conn:
        try:
            # Thiết kế read-only transaction với timeout 5 giây
            async with conn.transaction():
                await conn.execute("SET TRANSACTION READ ONLY;")
                await conn.execute("SET LOCAL statement_timeout = 5000;")
                rows = await conn.fetch(sql)
                return {"success": True, "data": [dict(r) for r in rows], "sql": sql}
        except Exception as db_err:
            # Bước 5: Nếu lỗi, thực hiện tự động sửa lỗi (Refine) đúng 1 lần duy nhất
            logging.warning(f"SQL execution failed: {db_err}. Retrying refinement...")
            refined_sql = await refine_sql(sql, str(db_err), llm_client)
            
            is_safe, error_msg = validate_sql(refined_sql)
            if not is_safe:
                return {"success": False, "error": f"Refined SQL validation failed: {error_msg}", "sql": refined_sql}
                
            try:
                rows = await conn.fetch(refined_sql)
                return {"success": True, "data": [dict(r) for r in rows], "sql": refined_sql}
            except Exception as retry_err:
                return {"success": False, "error": f"Execution failed after retry: {retry_err}", "sql": refined_sql}
```

---

### 3.4. Luồng Cập nhật Trạng thái Cam kết (Commitment Status Update Workflow)

Khi người dùng cập nhật trạng thái cam kết từ giao diện trợ lý ảo:
* Backend cung cấp API `PATCH /api/commitments/{passage_id}/{commitment_id}` thực thi ghi trên DB thông qua tài khoản ghi dữ liệu (`javis_etl`):
```python
# api/commitments.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal
import json

router = APIRouter()

class CommitmentStatusUpdate(BaseModel):
    status: Literal["pending", "done", "cancelled"]

@router.patch("/api/commitments/{commitment_id}")
async def update_commitment_status(
    commitment_id: str,
    body: CommitmentStatusUpdate,
    db_pool = Depends(get_write_db_pool) # Sử dụng pool ghi
):
    async with db_pool.acquire() as conn:
        # Cập nhật trực tiếp trạng thái trên bảng commitments đã chuẩn hóa
        result = await conn.execute(
            "UPDATE commitments SET status = $1 WHERE id = $2",
            body.status, commitment_id
        )
        if result == "UPDATE 0":
            raise HTTPException(404, "Không tìm thấy cam kết tương ứng trong cuộc họp")
    return {"success": True, "commitment_id": commitment_id, "status": body.status}
```

---

## 4. Xử lý Đa ngôn ngữ (Tiếng Nhật & Tiếng Việt)

* **Ingestion-time (Nạp):** 
  * Sử dụng thư viện `SudachiPy` (tiếng Nhật) và `Underthesea` (tiếng Việt) để chuẩn hóa văn bản trước khi đưa vào LLM Metadata Extraction.
  * Bảng `entity_aliases` sẽ chứa tất cả các dạng từ đồng nghĩa, tên viết tắt, dịch nghĩa của cả tiếng Việt và tiếng Nhật để chuẩn hóa metadata trước khi ghi nhận.
* **Query-time (Truy vấn):**
  * Tự động phát hiện ngôn ngữ câu hỏi (`vi` hoặc `ja`).
  * System Prompt được viết bằng tiếng Anh để mô hình hoạt động ổn định và chính xác nhất cho cả 2 ngôn ngữ.

---

## 5. Chiến lược Lựa chọn Mô hình (Tiered Model Strategy)

Để tối ưu hóa chi phí API LLM, hệ thống sử dụng chiến lược mô hình phân tầng:
* **Tier 1 (Mặc định):** Sử dụng **Gemini 2.5 Flash** hoặc **GPT-4o-mini** thông qua API. Tối ưu về chi phí, tốc độ và khả năng hiểu đa ngôn ngữ vượt trội.
* **Tier 2 (Fallback):** Sử dụng **Gemini 2.5 Pro** hoặc **GPT-4o** khi Tier 1 thất bại sau 1 lần tự sửa lỗi, hoặc khi phát hiện câu hỏi thuộc lớp cực kỳ phức tạp (nhiều điều kiện lồng nhau).

---

## 6. Bảo mật và Xử lý Lỗi

### 6.1. Bảo mật
* **Read-Only User:** User kết nối DB của phân hệ truy vấn chỉ được cấp quyền `SELECT` trên các Views (`v_*`).
* **SQL Whitelist & Injection Defense:** Chặn mọi ký tự lạ và câu lệnh ngoài whitelist `SELECT` thông qua AST Parser của `sqlglot`.
* **Data Minimization:** Chỉ gửi schema định nghĩa View và giá trị thực thể ánh xạ tới API của LLM bên thứ ba, không gửi nội dung hội thoại thực tế của cuộc họp.

### 6.2. Lỗi và Fallback
* Khi Agent truy vấn SQL thất bại (sau retry hoặc timeout), module trả về phản hồi `success = false`.
* Hệ thống Javis tổng thể sẽ bắt sự kiện này để **tự động chuyển hướng (fallback)** sang phân hệ Hybrid Vector RAG, đồng thời hiển thị cảnh báo mức độ tin cậy thấp đối với các số liệu được trích xuất.

---

## 7. Kế hoạch Triển khai Phân tầng (Implementation Phases)

Thay vì dựng một kiến trúc phức tạp ngay từ đầu, dự án Javis sẽ phân chia kế hoạch triển khai thành 3 tầng ưu tiên từ thấp lên cao:

### Tầng 1: Core Infrastructure (Tuần 1-2)
*Mục tiêu: Dựng thành công môi trường dữ liệu quan hệ và nạp được dữ liệu.*
- [ ] Chạy các migration script tạo cấu trúc DB (tables, views, indexes).
- [ ] Seed dữ liệu ban đầu cho bảng `entity_aliases` (tên công ty, tên người Việt/Nhật).
- [ ] Xây dựng code nạp dữ liệu ETL cơ bản: Rule-based chunker + LLM enrichment + Pydantic validation (với ID cam kết và gán status ở loader).
- [ ] Verify dữ liệu: Query thủ công trên các view `v_commitments`, `v_amounts`, `v_speaker_turns` đảm bảo dữ liệu hiển thị chính xác.

### Tầng 2: Routing Node + Text2SQL cơ bản (Tuần 3-4)
*Mục tiêu: Hoàn thiện luồng truy vấn tuyến tính đơn giản cho người dùng.*
- [ ] Xây dựng và tinh chỉnh **Routing Node** để phân luồng câu hỏi RAG vs SQL chính xác.
- [ ] Viết hàm chạy **Text2SQL Pipeline tuyến tính** (không dùng LangGraph).
- [ ] Tích hợp 15 câu ví dụ mẫu (few-shot) chuẩn vào System Prompt của LLM sinh SQL.
- [ ] Triển khai tích hợp thư viện `sqlglot` để validate an toàn câu lệnh SQL.
- [ ] Triển khai cơ chế chạy thử SQL trên connection Read-only kèm theo 1-turn retry tự động sửa lỗi.

### Tầng 3: Nâng cao dựa trên Failure Patterns (Tuần 5+)
*Mục tiêu: Tối ưu hiệu năng, độ chính xác khi hệ thống đã có dữ liệu chạy thực tế.*
- [ ] Nâng cấp giải thuật **Temporal Resolution** và **Entity Mapper** bằng thư viện chuyên dụng hoặc tìm kiếm mờ (`pg_trgm`) nếu phát hiện tỷ lệ map thực thể bị sai cao.
- [ ] Nếu cơ chế retry 1 lần không đáp ứng đủ yêu cầu sửa các câu SQL phức tạp, nâng cấp pipeline từ tuyến tính lên **LangGraph Multi-node** có State.
- [ ] Thiết lập hệ thống cache kết quả bằng **Redis Cache** để giảm chi phí API LLM cho các câu hỏi trùng lặp.
- [ ] Triển khai **pgvector** cho bảng `golden_queries` để tìm kiếm động top-3 câu ví dụ tương đồng thay vì hardcode trong prompt.
- [ ] Viết bộ chạy đánh giá tự động (Evaluation Runner) với 86 test cases để tính toán điểm EX, VES và Latency của hệ thống.

---

## 8. Phụ lục: Danh sách Dữ liệu Mẫu (Sample Mock Data)

Hệ thống sử dụng 3 tệp dữ liệu mẫu sau để thực hiện thử nghiệm nạp dữ liệu (Ingestion) và chạy truy vấn (Testing):

1. **Thông tin VJ Technologies (Tiếng Nhật):** [VJ_technologies_ja.md](file:///d:/VJ/Tro-li-ao-Javis/docs/VJ_technologies_ja.md)  
   *Mục đích:* Dùng để thử nghiệm khả năng bóc tách thực thể tiếng Nhật, trích xuất chủ đề (AI, Microservices, Machine learning,...) và các sản phẩm phần mềm (DX-ASAP, Energy Japan, GoEMON Jobs,...) lưu vào bảng `passages` và `meetings`.

2. **Thông tin AJ Technologies (Tiếng Nhật):** [AJ_technologies_ja.md](file:///d:/VJ/Tro-li-ao-Javis/docs/AJ_technologies_ja.md)  
   *Mục đích:* Dùng để thử nghiệm trích xuất thực thể, mối quan hệ công ty con/đối tác (VJ Technologies, ONE Financial Service) và các tính năng AI của nền tảng "ホムすん" (AI OCR, Chatbot, Giọng nói & Ghi âm, Lập lịch tiến độ,...).

3. **Bản tóm tắt thương lượng/giao dịch (Tiếng Nhật):** [sumary_mau.md](file:///d:/VJ/Tro-li-ao-Javis/docs/sumary_mau.md)  
   *Mục đích:* Chứa thông tin về ngân sách (4,500万円), mốc thời gian (次回打ち合わせは５月３０日) và các đầu việc cam kết/giao hẹn (次回打ち合わせまでに資金計画書を作成する,...). Đây là tài liệu cốt lõi để kiểm thử tính năng trích xuất `commitments`, `amounts`, `dates_mentioned` và chạy truy vấn đếm/lọc SQL.

