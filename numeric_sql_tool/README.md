# Numeric SQL Tool

Công cụ CLI độc lập để trả lời **câu hỏi số liệu (numeric)** trên dữ liệu meeting transcript trong PostgreSQL. Pipeline dùng **LLM (Groq) + regex heuristic** để suy ra intent (JSON cố định), sau đó **sinh và chạy SQL template** — LLM **không** viết SQL tùy ý.

Phạm vi hiện tại: **nhánh Meeting Transcript** (3 cuộc họp từ file Excel test). Bảng `company_documents` / `company_chunks` có schema nhưng dữ liệu để trống.

---

## Tóm tắt những gì đã triển khai

### 1. Schema và dữ liệu meeting

| Bảng | Vai trò |
|------|---------|
| `transcripts` | Bảng gốc: 1 dòng = 1 cuộc họp (`meeting_date`, `duration_seconds`, `summary`, `raw_text`, …) |
| `chunks_passage` | Đoạn lớn trong meeting (theo chủ đề / agenda), FK → `transcripts` |
| `chunks_turn` | Từng lượt phát biểu (speaker, `time_start_sec`, `time_end_sec`), FK → `transcripts` + `chunks_passage` |

**Dữ liệu nguồn:** `db/Test javis chatbot.xlsx` — 3 sheet meeting:

- `meeting_01_20260526` (2026-05-26) — định kỳ: tiến độ ASR, ngân sách Q2, năng lượng  
- `meeting_02_20260520` (2026-05-20) — review Q1, marketing Q2, tuyển dụng  
- `meeting_03_20260515` (2026-05-15) — launch AiVoice Pro  

**Thống kê sau khi generate:**

| Meeting | Turns | Passages | Thời lượng (giây) |
|---------|-------|----------|-------------------|
| meeting_01_20260526 | 58 | 5 | 1,855 |
| meeting_02_20260520 | 74 | 5 | 2,702 |
| meeting_03_20260515 | 99 | 7 | 3,610 |

`user_id` mặc định: `00000000-0000-0000-0000-000000000000`.

### 2. Script sinh SQL từ Excel

`scripts/generate_meeting_sql.py`:

- Đọc cột tiếng Nhật trong Excel (`[HH:MM:SS-HH:MM:SS][話者] …`).
- Tạo `db/data/transcripts.sql`, `chunks_passage.sql`, `chunks_turn.sql`.
- **Chia passage** theo câu chuyển agenda (ví dụ `予算の話に移りましょう`), không gom cả meeting vào 1 passage.

### 3. Load data an toàn (thứ tự FK)

`src/numeric_sql_tool/db_utils.py` load file theo thứ tự:

1. `transcripts.sql`  
2. `chunks_passage.sql`  
3. `chunks_turn.sql`  
4. `company_documents.sql` / `company_chunks.sql` (hiện rỗng)

Tránh lỗi FK khi insert `chunks_passage` trước `transcripts`.

### 4. Pipeline numeric

`src/numeric_sql_tool/pipeline.py`:

1. `extract_numeric_intent` — Groq structured output + fallback regex (`heuristics.py`).  
2. `resolve_date_range` — 今月 / 昨日 / 今週 / ngày `YYYY-MM-DD` trong câu hỏi.  
3. Chạy SQL template trên `transcripts` (và join `chunks_turn` khi `group_by=speaker`).  
4. Trả JSON: `rows`, `metadata.sql`, `operator`, `target`.

Hỗ trợ: `meeting_count`, `duration_seconds` (sum/avg/max/min), `group_by` day/speaker/user_id. Câu timestamp (何分頃に発言) → **SKIP** (không phải numeric SQL).

`build_numeric_sql(intent)` — xem SQL sẽ chạy mà không cần DB (dùng cho export test).

### 5. CLI

| Lệnh | Mô tả |
|------|--------|
| `init-db` | Tạo bảng từ `db/schema.sql` |
| `load-data` | Nạp `db/data/*.sql` |
| `numeric` | Một câu hỏi → chạy pipeline, in JSON |
| `batch` | Đọc file `.txt` nhiều câu → Excel (`question`, `sql`) |

### 6. Test case tiếng Nhật và Báo cáo Đánh giá (Evaluation Results)

| File / Thư mục | Mô tả |
|------|--------|
| `eval/numeric_sql_testcases_ja.csv` | 200 test cases tiếng Nhật chuẩn với kỳ vọng (SQL hoặc SKIP). |
| `scripts/eval_cases.py` | Script kiểm thử tĩnh (Heuristics vs CSV). Đạt độ chính xác **100.00%** (200/200). |
| `scripts/eval_hybrid.py` | Script kiểm thử thực tế (Hybrid Pipeline vs CSV + PostgreSQL). Đạt độ chính xác **100.00%** (200/200). |
| `eval/evaluation_report.md` | Báo cáo chi tiết của kiểm thử tĩnh. |
| `eval/evaluation_report_hybrid.md` | Báo cáo chi tiết của kiểm thử động thực tế (LLM Groq Llama 3 + Heuristic fallback). |
| `db/reset_meeting_data.sql` | `TRUNCATE` 3 bảng meeting trước khi load lại. |

---

## Kiến trúc dữ liệu (Meeting Transcript)

```
transcripts (1 meeting)
    │
    ├── chunks_passage (N đoạn: opening, budget, …)
    │       │
    │       └── chunks_turn (M lượt phát biểu)
    │
    └── raw_text / summary / duration_seconds
```

**Luồng pipeline:**

```
Câu hỏi (JA)
    → LLM intent (Groq) hoặc regex fallback
    → resolve_date_range (optional)
    → SQL template + params ($1 user, $2 date_start, $3 date_end, $4 context_filter)
    → PostgreSQL
    → JSON kết quả
```

---

## Cấu trúc thư mục

```
numeric_sql_tool/
├── db/
│   ├── schema.sql
│   ├── reset_meeting_data.sql
│   ├── Test javis chatbot.xlsx      # nguồn meeting
│   ├── numeric_sql_questions_ja.txt
│   ├── numeric_sql_testcases_ja.xlsx
│   └── data/
│       ├── transcripts.sql
│       ├── chunks_passage.sql
│       ├── chunks_turn.sql
│       ├── company_documents.sql    # rỗng
│       └── company_chunks.sql         # rỗng
├── scripts/
│   ├── generate_meeting_sql.py
│   ├── ja_testcases.py
│   └── export_numeric_sql_testcases.py
├── src/numeric_sql_tool/
│   ├── cli.py
│   ├── pipeline.py
│   ├── heuristics.py
│   ├── models.py
│   ├── config.py
│   └── groq_client.py
├── docker-compose.yml
├── .env.example
├── pyproject.toml
└── README.md
```

---

## Yêu cầu

- Python 3.11+
- Docker (PostgreSQL)
- API key Groq (khi chạy pipeline **có LLM**, không bắt buộc với `--regex-only`)

---

## Cài đặt từng bước

### Bước 1 — Clone / vào thư mục và tạo venv

```powershell
cd d:\javis_text2sql\numeric_sql_tool
python -m venv ..\.venv
..\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e .
pip install openpyxl pandas   # cho script Excel / testcases
```

### Bước 2 — Cấu hình môi trường

```powershell
Copy-Item .env.example .env
```

Chỉnh `.env`:

```env
NUMERIC_SQL_DATABASE_URL=postgresql://app_user:app_password@localhost:54331/app_db
GROQ_API_KEYS=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
NUMERIC_SQL_LLM_PROVIDER=groq
NUMERIC_SQL_STATEMENT_TIMEOUT_MS=5000
```

### Bước 3 — Khởi động PostgreSQL

```powershell
docker compose up -d
```

Port host: **54331** → container 5432.

### Bước 4 — Tạo schema

```powershell
numeric-sql-tool init-db
```

### Bước 5 — (Tùy chọn) Tạo lại dữ liệu SQL từ Excel

Chỉ cần khi bạn sửa file `db/Test javis chatbot.xlsx`:

```powershell
python scripts\generate_meeting_sql.py
```

### Bước 6 — Nạp dữ liệu meeting

Nếu đã `load-data` trước đó và bị duplicate key, truncate trước:

```powershell
Get-Content db\reset_meeting_data.sql | docker compose exec -T postgres psql -U app_user -d app_db
numeric-sql-tool load-data
```

Kết quả mong đợi: áp dụng `transcripts.sql` → `chunks_passage.sql` → `chunks_turn.sql` (và file company rỗng).

### Bước 7 — Chạy thử một câu hỏi

**Chỉ cần câu hỏi** (các tham số khác có mặc định):

```powershell
numeric-sql-tool numeric --question "今月は会議が何回ありますか？"
```

**Khuyến nghị** khi data test nằm trong **tháng 5/2026** và câu có 今月 / 昨日 / 今週:

```powershell
numeric-sql-tool numeric --question "今月は会議が何回ありますか？" --reference-date 2026-05-28
```

Không truyền `--reference-date` → dùng **ngày hôm nay của máy** để hiểu 今月・昨日 (có thể lệch so với data test).

---

## Lệnh CLI chi tiết

### `numeric` — một câu hỏi

```powershell
numeric-sql-tool numeric --question "質問文"
```

| Tham số | Mặc định | Ghi chú |
|---------|----------|---------|
| `--question` | (bắt buộc*) | *Hoặc pipe qua stdin |
| `--reference-date` | Hôm nay | `YYYY-MM-DD` cho 今月・昨日・今週 |
| `--user-id` | `00000000-0000-0000-0000-000000000000` | Lọc `transcripts.user_id` |
| `--date-start` / `--date-end` | Không ép | Ghi đè khoảng ngày |
| `--regex-only` | Tắt | Bật = không gọi Groq (tránh 429) |
| `--allow-cross-user` | Tắt | Cho phép group theo `user_id` |

Ví dụ stdin:

```powershell
"5月26日の会議件数は？" | numeric-sql-tool numeric
```

Output JSON gồm `rows`, `metadata.sql`, `operator`, `target`.

### `batch` — nhiều câu từ file `.txt` → Excel

```powershell
numeric-sql-tool batch `
  --questions-file db\numeric_sql_questions_ja.txt `
  --out db\numeric_sql_testcases_ja.xlsx `
  --reference-date 2026-05-28 `
  --concurrency 1 `
  --delay-ms 1500
```

- `--concurrency 1` + `--delay-ms` cao → giảm lỗi **429** Groq.  
- `--regex-only` → không gọi LLM, chỉ heuristic.

### Chạy từng câu thủ công (tránh 429)

```powershell
Get-Content db\numeric_sql_questions_ja.txt | ForEach-Object {
  $q = $_.Trim()
  if (-not $q -or $q.StartsWith("#")) { return }
  numeric-sql-tool numeric --question $q
  Start-Sleep -Seconds 2
}
```

---

## Script hỗ trợ

### Sinh 100 câu hỏi JA (file `.txt`)

```powershell
python scripts\ja_testcases.py generate
# → db/numeric_sql_questions_ja.txt
```

### Chạy pipeline → Excel

```powershell
python scripts\ja_testcases.py run --reference-date 2026-05-28 --delay-ms 1500
# hoặc
python scripts\ja_testcases.py all --reference-date 2026-05-28
```

### Export SQL chỉ regex (không DB, không Groq)

```powershell
python scripts\export_numeric_sql_testcases.py --reference-date 2026-05-28
# → db/numeric_sql_testcases.xlsx
```

---

## Ví dụ câu hỏi và kết quả mong đợi (data test)

| Câu hỏi | Kỳ vọng (reference-date 2026-05-28) |
|---------|-------------------------------------|
| `今月は会議が何回ありますか？` | `value = 3` (tháng 5) |
| `私が参加した中で、最も長かった会議は？` | meeting 2026-05-15, ~3610 giây |
| `昨日、何か会議はありましたか？` | 2026-05-27 → 0 meeting |
| `佐藤…何分頃に発言…` | SKIP (không phải numeric) |

Tham chiếu thêm sheet **Test** trong file Excel gốc.

---

## SQL và tham số

Mọi query numeric dùng WHERE chung:

- `$1` — `user_id` (UUID)  
- `$2` — `date_start` (nullable)  
- `$3` — `date_end` (nullable)  
- `$4` — `context_filter` (nullable, ILIKE trên `summary` / `raw_text`)

---

## Xử lý sự cố

| Vấn đề | Cách xử lý |
|--------|------------|
| `ForeignKeyViolation` khi `load-data` | Chạy `db/reset_meeting_data.sql` rồi `load-data` lại |
| `duplicate key transcripts_pkey` | Truncate như trên |
| Groq **429 Rate Limit** | Chạy từng câu; `batch --concurrency 1 --delay-ms 2000`; hoặc `--regex-only` |
| `今月` trả về 0 meeting | Thêm `--reference-date 2026-05-28` |
| `GROQ_API_KEYS is required` | Điền `.env` hoặc dùng `--regex-only` |
| Unicode lỗi trên console Windows | `$env:PYTHONIOENCODING='utf-8'` |

---

## Giới hạn hiện tại

- Chỉ **numeric aggregation** trên metadata meeting; câu semantic / tóm tắt / “ai nói gì” cần module khác (RAG / hybrid).  
- `context_filter` trong SQL phụ thuộc LLM gán intent; regex-only thường **không** lọc theo chủ đề (予算, 音声認識, …).  
- Passage split dựa vào **cụm từ chuyển agenda** trong transcript; meeting không có câu chuyển đoạn sẽ khó tách passage.  
- Nhánh **company** chưa có dữ liệu.

---

## Phát triển tiếp (gợi ý)

- Thêm `NUMERIC_SQL_REFERENCE_DATE` trong `.env` để không phải truyền tay `--reference-date`.  
- Mở rộng heuristic / LLM cho `context_filter` từ keyword tiếng Nhật.  
- Query trực tiếp trên `chunks_turn` cho câu hỏi theo speaker / thời gian phát biểu.
