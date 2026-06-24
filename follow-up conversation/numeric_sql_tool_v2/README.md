# Numeric SQL Tool

Công cụ CLI độc lập để trả lời **câu hỏi số liệu (numeric)** trên dữ liệu meeting transcript trong PostgreSQL. Pipeline dùng **LLM (Groq) + regex heuristic** để suy ra intent (JSON cố định), sau đó **sinh và chạy SQL template** — LLM **không** viết SQL tùy ý.

Phạm vi hiện tại: **nhánh Meeting Transcript** — dữ liệu chuẩn từ `dump-app_db-202606041640.sql` (leader): 9 transcript `data_docs` (`ingest-media-gt_01`…`09`, tháng 5/2026) + 3 meeting (`ingest-meeting-01/02/03`) + chat history mẫu.

---

## Tóm tắt những gì đã triển khai

### 1. Schema và dữ liệu meeting

| Bảng | Vai trò |
|------|---------|
| `transcripts` | Bảng gốc: 1 dòng = 1 cuộc họp (`meeting_date`, `duration_seconds`, `summary`, `raw_text`, …) |
| `chunks_passage` | Đoạn lớn trong meeting (theo chủ đề / agenda), FK → `transcripts` |
| `chunks_turn` | Từng lượt phát biểu (speaker, `time_start_sec`, `time_end_sec`), FK → `transcripts` + `chunks_passage` |

**Dữ liệu nguồn (leader dump):**

| `data_docs` | `session_id` trong DB | `meeting_date` |
|-------------|----------------------|----------------|
| script1 | `ingest-media-gt_01-2026-05-01` | 2026-05-01 |
| script2 | `ingest-media-gt_02-2026-05-02` | 2026-05-02 |
| … | … | … |
| script9 | `ingest-media-gt_09-2026-05-09` | 2026-05-09 |
| (meeting cũ) | `ingest-meeting-01-20260526` | 2026-05-26 |
| | `ingest-meeting-02-20260520` | 2026-05-20 |
| | `ingest-meeting-03-20260515` | 2026-05-15 |

Dump còn passages/turns đã enrich (LLM summary, `chunk_metadata` topics) — **không** dùng bản INSERT tự generate trong `db/data/` nếu cần khớp leader.

`user_id` mặc định (pipeline): `00000000-0000-0000-0000-000000000001`  
`project_id` transcript: `00000000-0000-0000-0000-000000000101`

### 2. Restore DB từ leader dump (khuyến nghị)

```powershell
docker compose up -d
numeric-sql-tool restore-db
# hoặc: python scripts/restore_db.py
```

Lệnh `restore-db` chạy `db/reset_all.sql` (DROP SCHEMA) rồi nạp `dump-app_db-202606041640.sql` qua `psql` trong container (hỗ trợ định dạng COPY).

`scripts/generate_meeting_sql.py` — chỉ để debug (INSERT đơn giản, UUID khác dump).

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
| `init-db` | Tạo bảng từ `db/schema.sql` (schema rỗng) |
| `restore-db` | Nạp **toàn bộ** leader dump (schema + data) |
| `load-data` | Nạp `db/data/*.sql` (legacy INSERT — không khớp dump) |
| `numeric` | Một câu hỏi → chạy pipeline, in JSON |
| `batch` | Đọc file `.txt` nhiều câu → Excel (`question`, `sql`) |

### 6. Test case tiếng Nhật và Báo cáo Đánh giá (Evaluation Results)

| File / Thư mục | Mô tả |
|------|--------|
| `eval/numeric_sql_testcases_ja.csv` | 100 test cases cơ bản (template-based). |
| `eval/new_100_advanced_testcases.csv` | 100 test cases nâng cao (phức tạp hơn). |
| `eval/stress_100_testcases_ja.csv` | 100 test cases stress test (kiểm tra độ bền, bẫy từ khóa). |
| `eval/combined_200_testcases_ja.csv` | **Bộ 200 test cases tổng hợp** (Cơ bản + Nâng cao). |
| `eval/combined_300_testcases_ja.csv` | **Bộ 300 test cases tổng hợp** (Cơ bản + Nâng cao + Stress test). |
| `scripts/temp_eval.py` | Script đánh giá Heuristics vs Kết quả thực tế (CSV). Hỗ trợ `--gt`, `--actual` và `--out`. |
| `eval/evaluation_report_300_honest.md` | Báo cáo chi tiết cho bộ 300 test cases. |

---

## Quy trình Kiểm thử mở rộng (300 Test Cases)

Để đảm bảo độ bao phủ, chúng ta sử dụng bộ 300 test cases (100 cơ bản + 100 nâng cao + 100 stress test, loại trừ 100 random test cases).

### Bước 1: Chuẩn bị file câu hỏi
Nếu chưa có file `db/questions_300_ja.txt`, trích xuất từ file CSV tổng hợp:
```powershell
python -c "import pandas as pd; df = pd.read_csv('eval/combined_300_testcases_ja.csv'); df['question'].to_csv('db/questions_300_ja.txt', index=False, header=False, encoding='utf-8')"
```

### Bước 2: Chạy Pipeline để sinh kết quả (Test Run)

#### Cách A: Chạy chế độ Hybrid (Có LLM + Regex Fallback)
*(Cần cấu hình `GROQ_API_KEYS` trong file `.env` và có delay để tránh Rate Limit 429)*
```powershell
python scripts/ja_testcases.py run `
  --questions db/questions_300_ja.txt `
  --excel-out db/numeric_sql_testcases_300_ja.xlsx `
  --reference-date 2026-05-28 `
  --concurrency 1 `
  --delay-ms 1200
```

#### Cách B: Chạy chế độ Regex-Only (Không dùng LLM)
*(Chạy cực nhanh, không lo Rate Limit)*
```powershell
python scripts/ja_testcases.py run `
  --questions db/questions_300_ja.txt `
  --excel-out db/numeric_sql_testcases_300_ja.xlsx `
  --reference-date 2026-05-28 `
  --regex-only `
  --concurrency 10 `
  --delay-ms 0
```

### Bước 3: Chạy Đánh giá và Đối soát (Evaluation & Audit)

Sau khi sinh ra kết quả tại `db/numeric_sql_testcases_300_ja.xlsx`, chạy các script đánh giá sau:

#### 1. Tạo Báo cáo Đánh giá Trung thực:
```powershell
python scripts/temp_eval.py `
  --actual db/numeric_sql_testcases_300_ja.xlsx `
  --gt eval/combined_300_testcases_ja.csv `
  --out eval/evaluation_report_300_honest.md
```
Báo cáo chi tiết sẽ được ghi nhận tại `eval/evaluation_report_300_honest.md`.

#### 2. Tạo Báo cáo Đối soát Trung thực:
```powershell
python scripts/audit_test_results.py `
  --actual db/numeric_sql_testcases_300_ja.xlsx `
  --gt eval/combined_300_testcases_ja.csv `
  --out eval/audit_report_300.md
```
Báo cáo đối soát (tập trung vào các trường hợp sai lệch/Discrepancies) sẽ được tạo tại `eval/audit_report_300.md`.

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

### Bước 4 — Nạp DB từ leader dump

```powershell
numeric-sql-tool restore-db
```

(Không cần `init-db` trước — dump đã có CREATE TABLE. Nếu chỉ cần schema rỗng: `init-db`.)

### Bước 5 — Chạy thử một câu hỏi

**Chỉ cần câu hỏi** (các tham số khác có mặc định):

```powershell
numeric-sql-tool numeric --question "今月は会議が何回ありますか？"
```

**Khuyến nghị** khi dùng leader dump (data tháng **5/2026**) và câu có 今月 / 昨日 / 今週:

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
| `--user-id` | `00000000-0000-0000-0000-000000000001` | Lọc `transcripts.user_id` (leader dump) |
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
| `今月は会議が何回ありますか？` | `value = 12` (user `...001`: 9 media + 3 meeting; bản ghi `2026-05-29` thuộc user khác) |
| `5月15日の会議の所要時間は何秒ですか？` | `value = 3610` (AiVoice Pro meeting) |
| `5月26日の定例会議の合計会議時間は何秒ですか？` | `value = 1855` |
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
| `今月` trả về 0 meeting | Thêm `--reference-date 2026-05-28` và `--user-id 00000000-0000-0000-0000-000000000001` |
| `GROQ_API_KEYS is required` | Điền `.env` hoặc dùng `--regex-only` |
| Unicode lỗi trên console Windows | `$env:PYTHONIOENCODING='utf-8'` |

---

## Giới hạn hiện tại

- Chỉ **numeric aggregation** trên metadata meeting; câu semantic / tóm tắt / “ai nói gì” cần module khác (RAG / hybrid).  
- `context_filter` trong SQL phụ thuộc LLM gán intent; regex-only thường **không** lọc theo chủ đề (予算, 音声認識, …).  
- `script9` trong dump có `status=failed` (timestamp `.mmm`) — vẫn đếm trong `meeting_count` nếu có `meeting_date`.  
- Bộ eval CSV (300 cases) ground-truth chủ yếu 3 meeting; câu về 9 cuộc gọi cần GT mới.  
- Nhánh **company** chưa có dữ liệu.

---

## Phát triển tiếp (gợi ý)

- Thêm `NUMERIC_SQL_REFERENCE_DATE` trong `.env` để không phải truyền tay `--reference-date`.  
- Mở rộng heuristic / LLM cho `context_filter` từ keyword tiếng Nhật.  
- Query trực tiếp trên `chunks_turn` cho câu hỏi theo speaker / thời gian phát biểu.
