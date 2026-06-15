# Numeric SQL Tool — Tài Liệu Kỹ Thuật

Công cụ aggregate meeting metadata bằng SQL có kiểm soát. LLM **không sinh SQL** — chỉ điền vào một form JSON cố định (`NumericIntent`), Python dùng form đó để chọn SQL template và chạy.

---

## Mục Lục

1. [Tổng quan luồng](#1-tổng-quan-luồng)
2. [NumericIntent — Trái tim của hệ thống](#2-numericintent--trái-tim-của-hệ-thống)
3. [Parse Intent — Ai điền form?](#3-parse-intent--ai-điền-form)
4. [SQL được sinh ra](#4-sql-được-sinh-ra)
5. [NumericResult — Output](#5-numericresult--output)
6. [Ví dụ đầy đủ end-to-end](#6-ví-dụ-đầy-đủ-end-to-end)
7. [Giới hạn](#7-giới-hạn)

---

## 1. Tổng Quan Luồng

```
Câu hỏi người dùng
        │
        ▼
[Parse Intent]
  ├─ Bước 1: Regex/heuristic thử đoán trước (nhanh, không tốn token)
  └─ Bước 2: LLM bổ sung nếu regex chưa đủ (regex thắng khi conflict)
        │
        ▼
NumericIntent { operator, target, group_by }
        │
        ├─ operator = "skip"? ──► Dừng, không chạy SQL
        │
        ├─ Validate quyền (user filter, cross-user guard)
        │
        ├─ target = duration_seconds + operator là max/min?
        │       └──► _run_duration_extreme() — trả về info đầy đủ của meeting
        │
        └─ Còn lại ──► _run_meeting() — chọn SQL template theo group_by
                │
                ▼
          NumericResult { operator, target, rows[] }
```

---

## 2. NumericIntent — Trái Tim Của Hệ Thống

Form JSON mà LLM/regex điền vào. Chỉ có 4 trường:

```python
class NumericIntent(BaseModel):
    operator: Literal["sum", "avg", "max", "min", "count", "skip", "none"]
    target:   Literal["duration_seconds", "meeting_count", "time_start_sec", "none"]
    group_by: Literal["none", "user_id", "day", "speaker"] = "none"
    context_filter: str | None = None
```

### `operator` — Làm gì với con số?

| Giá trị | Ý nghĩa | SQL |
|---|---|---|
| `sum` | Tổng | `SUM(...)` |
| `avg` | Trung bình | `AVG(...)` |
| `max` | Lớn nhất | `MAX(...)` hoặc `ORDER BY DESC LIMIT 1` |
| `min` | Nhỏ nhất | `MIN(...)` hoặc `ORDER BY ASC LIMIT 1` |
| `count` | Đếm số lượng | `COUNT(DISTINCT t.id)` |
| `skip` | Không cần SQL | Trả về sớm, không chạy gì |

### `target` — Đếm / tính cái gì?

| Giá trị | Ý nghĩa | Cột SQL |
|---|---|---|
| `meeting_count` | Số buổi họp | `COUNT(DISTINCT t.id)` trên `transcripts` |
| `duration_seconds` | Thời lượng họp (giây) | `t.duration_seconds` trên `transcripts` |
| `time_start_sec` | Timestamp phát biểu | *(chưa có template — tự động skip)* |
| `none` | Không xác định được | Tự động skip |

### `group_by` — Nhóm kết quả theo gì?

| Giá trị | Ý nghĩa | Ví dụ output |
|---|---|---|
| `none` | Không nhóm — 1 con số duy nhất | `{ value: 42 }` |
| `day` | Nhóm theo ngày | `{ "2026-05-26": 2, "2026-05-27": 1 }` |
| `speaker` | Nhóm theo người tham dự | `{ "田中": 5, "佐藤": 3 }` |
| `user_id` | Nhóm theo user *(chỉ admin)* | `{ "user-001": 10, "user-002": 7 }` |

---

## 3. Parse Intent — Ai Điền Form?

Có 2 tầng, chạy theo thứ tự:

### Tầng 1 — Regex (luôn chạy trước)

Nhanh, deterministic, không tốn token. Nhận ra các pattern tiếng Nhật phổ biến:

| Pattern regex | operator | target |
|---|---|---|
| `何時間`, `所要時間`, `合計時間` | `sum` | `duration_seconds` |
| `平均` | `avg` | `duration_seconds` |
| `最も長`, `一番長`, `最長` | `max` | `duration_seconds` |
| `最も短`, `一番短`, `最短` | `min` | `duration_seconds` |
| `何件`, `何回`, `件数`, `会議数` | `count` | `meeting_count` |
| `会議はありましたか`, `何か会議` | `count` | `meeting_count` |
| `何分頃`, `何秒頃`, `いつ発言` | `skip` | `none` |
| `ユーザーごと`, `ユーザー別` | *(giữ nguyên)* | group_by=`user_id` |
| `日ごと`, `日別` | *(giữ nguyên)* | group_by=`day` |
| `話者ごと`, `話者別` | *(giữ nguyên)* | group_by=`speaker` |

### Tầng 2 — LLM (bổ sung nếu cần)

Gọi sau regex nếu câu hỏi phức tạp hơn. Nhưng output LLM bị kiểm tra lại:

```
Nếu LLM trả "none"        → đổi thành "skip" (tránh crash schema)
Nếu LLM trả intent rỗng   → dùng kết quả regex luôn
Nếu regex tự tin về operator (khác "sum") mà LLM trả "sum" → giữ của regex
Nếu regex tự tin về target  (khác "meeting_count") mà LLM trả "meeting_count" → giữ của regex
Nếu LLM crash              → dùng kết quả regex, không raise error
```

**Nguyên tắc:** Regex thắng khi có conflict. LLM chỉ bổ sung những gì regex bỏ sót.

---

## 4. SQL Được Sinh Ra

WHERE clause **cố định** trong mọi query, chỉ thay params:

```sql
(:uid IS NULL OR t.user_id = CAST(:uid AS uuid))
AND (:ds IS NULL OR t.meeting_date >= :ds)
AND (:de IS NULL OR t.meeting_date <= :de)
```

`uid`, `ds`, `de` lấy từ query metadata (đã được resolve trước, ví dụ "昨日" → `2026-05-27`).

### 4a. `target = meeting_count`

```sql
SELECT COUNT(DISTINCT t.id) AS value
FROM transcripts t
WHERE <where_clause>
```

### 4b. `target = duration_seconds` + `operator` là `sum/avg`

```sql
SELECT COALESCE(SUM(t.duration_seconds), 0) AS value  -- hoặc AVG
FROM transcripts t
WHERE <where_clause>
```

### 4c. `target = duration_seconds` + `operator` là `max/min` *(nhánh đặc biệt)*

Không dùng `MAX()` — thay vào đó lấy cả hàng để biết **cuộc họp nào**:

```sql
SELECT
    t.id::text         AS transcript_id,
    t.session_id       AS session_id,
    t.meeting_date     AS meeting_date,
    t.participants     AS participants,
    t.duration_seconds AS value,
    t.summary          AS summary
FROM transcripts t
WHERE <where_clause>
  AND t.duration_seconds IS NOT NULL
ORDER BY t.duration_seconds DESC  -- ASC cho min
LIMIT 1
```

### 4d. Với `group_by = day`

```sql
SELECT t.meeting_date::text AS group_key,
       <value_expr>         AS value
FROM transcripts t
WHERE <where_clause>
GROUP BY t.meeting_date
ORDER BY group_key
LIMIT 31
```

### 4e. Với `group_by = speaker`

```sql
SELECT x.speaker AS group_key,
       <value_expr> AS value
FROM transcripts t
JOIN (
    SELECT DISTINCT transcript_id, speaker FROM chunks_turn
) x ON x.transcript_id = t.id
WHERE <where_clause>
GROUP BY x.speaker
ORDER BY value DESC
LIMIT 20
```

> ⚠️ `speaker` ở đây là người **tham dự meeting**, không phải tổng thời lượng phát biểu của từng người. Aggregate vẫn tính trên metadata của meeting (`duration_seconds`, `COUNT`), chỉ group theo speaker.

### 4f. Với `group_by = user_id` *(chỉ admin)*

```sql
SELECT t.user_id::text AS group_key,
       <value_expr>    AS value
FROM transcripts t
WHERE <where_clause>
GROUP BY t.user_id
ORDER BY value DESC
LIMIT 20
```

---

## 5. NumericResult — Output

```python
class NumericRow(BaseModel):
    group_key: str | None = None   # None nếu không group
    value: float
    metadata: dict = {}            # chỉ có ở nhánh duration_extreme

class NumericResult(BaseModel):
    operator: str
    target: str
    rows: list[NumericRow]
    source_chunk_ids: list[str] = []  # transcript_id (chỉ ở duration_extreme)
    metadata: dict = {}
```

**Output không group (1 con số):**

```json
{
  "operator": "sum",
  "target": "duration_seconds",
  "rows": [{ "group_key": null, "value": 7200.0 }]
}
```

**Output có group:**

```json
{
  "operator": "count",
  "target": "meeting_count",
  "rows": [
    { "group_key": "2026-05-26", "value": 2.0 },
    { "group_key": "2026-05-27", "value": 1.0 }
  ]
}
```

**Output duration_extreme (max/min):**

```json
{
  "operator": "max",
  "target": "duration_seconds",
  "rows": [{
    "value": 3610.0,
    "metadata": {
      "transcript_id": "b98bb910-...",
      "meeting_date": "2026-05-26",
      "participants": ["田中", "鈴木", "佐藤", "山田"],
      "summary": "2026年5月26日の定例会議では..."
    }
  }],
  "source_chunk_ids": ["b98bb910-..."]
}
```

**Output skip:**

```json
{
  "operator": "skip",
  "target": "none",
  "metadata": { "skipped": true }
}
```

---

## 6. Ví Dụ Đầy Đủ End-to-End

### Ví dụ 1 — Đếm meeting hôm qua

```
Input:  "昨日、何か会議はありましたか？"
Today:  2026-05-28
```

**Parse:**

```
regex: _EXISTENCE_RE match "何か会議" → operator=count, target=meeting_count
date:  "昨日" → date_start = date_end = 2026-05-27
```

**Intent:**

```json
{ "operator": "count", "target": "meeting_count", "group_by": "none" }
```

**SQL:**

```sql
SELECT COUNT(DISTINCT t.id) AS value
FROM transcripts t
WHERE t.user_id = '00000000-...'
  AND t.meeting_date >= '2026-05-27'
  AND t.meeting_date <= '2026-05-27'
```

**Result (nếu không có meeting ngày đó):**

```json
{ "rows": [{ "value": 0.0 }] }
```

**Final answer:** *"昨日（5月27日）は会議がありませんでした。"*

---

### Ví dụ 2 — Tổng thời lượng tháng 5

```
Input:  "5月の会議は合計何時間ありましたか？"
```

**Parse:**

```
regex: "合計時間" → operator=sum, target=duration_seconds
date:  "5月" → date_start=2026-05-01, date_end=2026-05-31
```

**Intent:**

```json
{ "operator": "sum", "target": "duration_seconds", "group_by": "none" }
```

**SQL:**

```sql
SELECT COALESCE(SUM(t.duration_seconds), 0) AS value
FROM transcripts t
WHERE t.user_id = '00000000-...'
  AND t.meeting_date >= '2026-05-01'
  AND t.meeting_date <= '2026-05-31'
```

**Result:**

```json
{ "rows": [{ "value": 18450.0 }] }
```

**Final answer:** *"5月の会議の合計時間は約5時間7分（18,450秒）です。"*

---

### Ví dụ 3 — Cuộc họp dài nhất

```
Input:  "これまで参加した中で最も長かった会議はどれですか？"
```

**Parse:**

```
regex: _DURATION_MAX_RE match "最も長" → operator=max, target=duration_seconds
→ đi thẳng vào _run_duration_extreme()
```

**Intent:**

```json
{ "operator": "max", "target": "duration_seconds", "group_by": "none" }
```

**SQL:**

```sql
SELECT t.id::text, t.meeting_date, t.participants,
       t.duration_seconds AS value, t.summary
FROM transcripts t
WHERE t.user_id = '00000000-...'
  AND t.duration_seconds IS NOT NULL
ORDER BY t.duration_seconds DESC
LIMIT 1
```

**Result:**

```json
{
  "rows": [{
    "value": 3610.0,
    "metadata": {
      "meeting_date": "2026-05-26",
      "participants": ["田中", "鈴木", "佐藤", "山田"],
      "summary": "2026年5月26日の定例会議では..."
    }
  }]
}
```

**Final answer:** *"最も長かった会議は2026年5月26日の定例会議で、約1時間（3,610秒）でした。"*

---

### Ví dụ 4 — Câu hỏi bị skip

```
Input:  "佐藤さんは何分頃に発言しましたか？"
```

**Parse:**

```
regex: _TIMESTAMP_RE match "何分頃" → operator=skip, target=none
→ dừng ngay, không chạy SQL
```

**Intent:**

```json
{ "operator": "skip", "target": "none" }
```

**Result:**

```json
{ "operator": "skip", "metadata": { "skipped": true } }
```

Pipeline biết SQL không giúp được → chỉ dùng semantic retrieval (turn timestamps từ Qdrant) để trả lời.

---

### Ví dụ 5 — Số meeting nhóm theo ngày

```
Input:  "今月、日ごとに何件の会議がありましたか？"
```

**Parse:**

```
regex: "何件" → count/meeting_count; "日ごと" → group_by=day
date:  "今月" → 2026-05-01 đến 2026-05-31
```

**Intent:**

```json
{ "operator": "count", "target": "meeting_count", "group_by": "day" }
```

**SQL:**

```sql
SELECT t.meeting_date::text AS group_key,
       COUNT(DISTINCT t.id) AS value
FROM transcripts t
WHERE t.user_id = '00000000-...'
  AND t.meeting_date >= '2026-05-01'
  AND t.meeting_date <= '2026-05-31'
GROUP BY t.meeting_date
ORDER BY group_key
LIMIT 31
```

**Result:**

```json
{
  "rows": [
    { "group_key": "2026-05-15", "value": 1.0 },
    { "group_key": "2026-05-20", "value": 1.0 },
    { "group_key": "2026-05-26", "value": 1.0 }
  ]
}
```

---

## 7. Giới Hạn

| Câu hỏi | Lý do không làm được |
|---|---|
| "Sato nói bao nhiêu phút?" | Không có cột `speaker_duration` — chỉ có `duration_seconds` của cả meeting |
| "Tuần nào họp nhiều nhất?" | `group_by` không có option `week` |
| "Meeting nào có nhiều action items nhất?" | `action_item_count` không phải cột trong `transcripts` |
| "Tỉ lệ meeting có vượt ngân sách" | Cần 2 COUNT rồi chia — form chỉ có 1 operator |
| "Ngân sách Q2 là bao nhiêu?" | Số tiền nằm trong nội dung hội thoại, không phải metadata → route sang `retrieval_cascade` theo thiết kế |
| `group_by = user_id` | Chỉ admin — user thường bị `ForbiddenException` |
| `time_start_sec` | Có trong schema nhưng chưa có SQL template → tự động skip |
