# Danh sách các định dạng SQL (SQL Formats)

Tài liệu này liệt kê toàn bộ các định dạng SQL hiện đang được sử dụng trong công cụ `numeric_sql_tool`. Các truy vấn này được xây dựng động trong `src/numeric_sql_tool/pipeline.py` dựa trên ý định (intent) được phân tích từ ngôn ngữ tự nhiên.

> **Lưu ý quan trọng:** 
> - Mọi truy vấn đều chạy trong chế độ **READ ONLY** và bị giới hạn thời gian (mặc định 5s).
> - Hệ thống luôn lọc theo `user_id` ($1) để đảm bảo an toàn dữ liệu.
> - Các truy vấn cực trị (`max/min duration`) trả về metadata chi tiết, các truy vấn khác trả về giá trị số (`value`).

## 1. Thành phần chung: Câu điều kiện WHERE

Hầu hết các truy vấn đều tích hợp bộ lọc cơ bản sau:

```sql
($1::uuid IS NULL OR t.user_id = $1::uuid) -- Lọc theo User ID
AND ($2::date IS NULL OR t.meeting_date >= $2::date) -- Từ ngày
AND ($3::date IS NULL OR t.meeting_date <= $3::date) -- Đến ngày
AND ($4::text IS NULL OR t.summary ILIKE '%' || $4 || '%' OR t.raw_text ILIKE '%' || $4 || '%') -- Lọc ngữ cảnh
AND ($5::text IS NULL OR TRUE) -- Tham số Speaker (giữ chỗ cho CTE/Subquery)
AND ($6::text IS NULL OR TRUE) -- Tham số Keyword (giữ chỗ)
```

---

## 2. Truy vấn Scalar (Trả về 1 giá trị duy nhất)

Các truy vấn này trả về một cột `value`.

### A. Số lượng cuộc họp & Thời lượng (`target="meeting_count | duration_seconds"`)
Dành cho các câu hỏi tổng quát không phân nhóm.

- **Số lượng cuộc họp:** `SELECT COUNT(DISTINCT t.id)::float AS value FROM transcripts t WHERE {where_clause}`
- **Tổng thời lượng:** `SELECT COALESCE(SUM(t.duration_seconds), 0)::float AS value FROM transcripts t WHERE {where_clause}`
- **Thời lượng trung bình:** `SELECT COALESCE(AVG(t.duration_seconds), 0)::float AS value FROM transcripts t WHERE {where_clause}`

### B. Thời gian phát biểu (`target="speaking_time"`)
Tính tổng (`sum`) hoặc trung bình (`avg`) thời gian nói.

**Trường hợp có chỉ định Speaker ($5):** Sử dụng logic 2-tier (khớp tên hoặc khớp nội dung).
```sql
WITH speaker_resolved AS (
  (SELECT ct2.speaker FROM chunks_turn ct2 JOIN transcripts t2 ON ct2.transcript_id = t2.id
   WHERE ct2.speaker = $5::text AND {where_clause_t2} LIMIT 1)
  UNION ALL
  (SELECT ct2.speaker FROM chunks_turn ct2 JOIN transcripts t2 ON ct2.transcript_id = t2.id
   WHERE ct2.text ILIKE '%' || $5::text || '%' AND {where_clause_t2} ORDER BY ct2.time_start_sec ASC LIMIT 1)
  LIMIT 1
) 
SELECT COALESCE({AVG|SUM}(ct.time_end_sec - ct.time_start_sec), 0)::float AS value 
FROM chunks_turn ct 
JOIN transcripts t ON ct.transcript_id = t.id 
WHERE ct.speaker IN (SELECT speaker FROM speaker_resolved) AND {where_clause}
```

**Trường hợp không có Speaker:** Tính cho toàn bộ cuộc họp.
```sql
SELECT COALESCE({AVG|SUM}(ct.time_end_sec - ct.time_start_sec), 0)::float AS value 
FROM chunks_turn ct 
JOIN transcripts t ON ct.transcript_id = t.id 
WHERE {where_clause}
```

### C. Số lượt phát biểu (`target="turn_count"`)
Đếm số lần người nói lên tiếng. Sử dụng logic `speaker_resolved` tương tự như trên nếu có $5.
- **Có Speaker:** `SELECT COUNT(*)::float AS value FROM chunks_turn ct ... WHERE ct.speaker IN (SELECT speaker FROM speaker_resolved) AND {where_clause}`
- **Không Speaker:** `SELECT COUNT(*)::float AS value FROM chunks_turn ct JOIN transcripts t ON ct.transcript_id = t.id WHERE {where_clause}`

### D. Số lần đề cập từ khóa (`target="mention_count"`)
Đếm số lần một từ khóa ($6) xuất hiện trong các lượt nói (Case-Insensitive).
```sql
SELECT COALESCE(SUM(
  CASE WHEN $6::text IS NULL OR $6::text = '' THEN 0 
  ELSE (LENGTH(ct.text) - LENGTH(REPLACE(LOWER(ct.text), LOWER($6::text), ''))) / NULLIF(LENGTH($6::text), 0) 
  END
), 0)::float AS value 
FROM chunks_turn ct 
JOIN transcripts t ON ct.transcript_id = t.id 
WHERE {where_clause} AND ($6::text IS NULL OR ct.text ILIKE '%' || $6::text || '%')
```

---

## 3. Truy vấn hỗ trợ Phân nhóm (Group By)

Dành cho `target="meeting_count"` hoặc `"duration_seconds"`.

### Định nghĩa biểu thức giá trị (`value_expr`):
- **Meeting Count:** `COUNT(DISTINCT t.id)`
- **Duration Seconds (Sum):** `COALESCE(SUM(t.duration_seconds), 0)`
- **Duration Seconds (Avg):** `COALESCE(AVG(t.duration_seconds), 0)`

### Các kiểu phân nhóm:
| Kiểu (`group_by`) | Mẫu SQL (SELECT & GROUP BY) | Sắp xếp & Giới hạn |
| :--- | :--- | :--- |
| **Day** | `t.meeting_date::text AS group_key` | `ORDER BY group_key LIMIT 31` |
| **Week** | `DATE_TRUNC('week', t.meeting_date)::date::text AS group_key` | `ORDER BY group_key LIMIT 52` |
| **Month** | `TO_CHAR(t.meeting_date, 'YYYY-MM') AS group_key` | `ORDER BY group_key LIMIT 12` |
| **Speaker** | `x.speaker AS group_key` (JOIN `chunks_turn`) | `ORDER BY value DESC LIMIT 20` |
| **User ID** | `t.user_id::text AS group_key` | `ORDER BY value DESC LIMIT 20` |

---

## 4. Truy vấn Cực trị (Max/Min Duration)

Truy vấn này trả về danh sách Top-N các cuộc họp dựa trên thời lượng.

**Định dạng:**
```sql
SELECT t.id::text AS transcript_id, t.session_id AS session_id, 
       t.meeting_date::text AS meeting_date, t.participants AS participants, 
       t.duration_seconds AS value, t.summary AS summary 
FROM transcripts t 
WHERE {where_clause} AND t.duration_seconds IS NOT NULL 
ORDER BY t.duration_seconds {DESC|ASC}, t.meeting_date {DESC|ASC} 
LIMIT {limit}
```
*Lưu ý: `{limit}` mặc định là 1, nhưng có thể tăng lên nếu câu hỏi yêu cầu "Top 5", "3 cuộc họp dài nhất"...*

---

## 5. Danh sách tham số (Parameters)

| Tham số | Kiểu dữ liệu | Mô tả |
| :--- | :--- | :--- |
| `$1` | UUID | User ID (để cô lập dữ liệu theo người dùng) |
| `$2` | Date | Ngày bắt đầu lọc (date_start) |
| `$3` | Date | Ngày kết thúc lọc (date_end) |
| `$4` | Text | Từ khóa lọc ngữ cảnh (áp dụng cho summary và raw_text) |
| `$5` | Text | Tên speaker hoặc từ khóa tìm speaker (dùng trong CTE) |
| `$6` | Text | Từ khóa cụ thể cần đếm (dùng trong mention_count) |
