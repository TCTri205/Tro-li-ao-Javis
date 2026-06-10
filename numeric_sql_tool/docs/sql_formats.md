# Danh sách các định dạng SQL (SQL Formats)

Tài liệu này liệt kê toàn bộ các định dạng SQL hiện đang được sử dụng trong công cụ `numeric_sql_tool`. Các truy vấn này được xây dựng động trong `src/numeric_sql_tool/pipeline.py` dựa trên ý định (intent) được phân tích.

> **Lưu ý quan trọng:** Hiện tại, các mục tiêu như `speaking_time`, `turn_count`, `mention_count` và các cực trị `max/min duration` chỉ hỗ trợ trả về kết quả đơn lẻ (Scalar). Chỉ có `meeting_count` và `duration_seconds` (Sum/Avg) mới hỗ trợ phân nhóm (`group_by`).

## 1. Thành phần chung: Câu điều kiện WHERE

Hầu hết các truy vấn đều tích hợp bộ lọc cơ bản sau:

```sql
($1::uuid IS NULL OR t.user_id = $1::uuid) -- Lọc theo User ID
AND ($2::date IS NULL OR t.meeting_date >= $2::date) -- Từ ngày
AND ($3::date IS NULL OR t.meeting_date <= $3::date) -- Đến ngày
AND ($4::text IS NULL OR t.summary ILIKE '%' || $4 || '%' OR t.raw_text ILIKE '%' || $4 || '%') -- Lọc ngữ cảnh
AND ($5::text IS NULL OR TRUE) -- Tham số Speaker (giữ chỗ)
AND ($6::text IS NULL OR TRUE) -- Tham số Keyword (giữ chỗ)
```

---

## 2. Truy vấn Scalar (Trả về 1 giá trị duy nhất)

Các truy vấn này trả về một cột `value`.

### A. Thời gian phát biểu (`target="speaking_time"`)
Tính tổng (`sum`) hoặc trung bình (`avg`) thời gian nói của một người.

**Định dạng:**
```sql
SELECT COALESCE({AVG|SUM}(ct.time_end_sec - ct.time_start_sec), 0)::float AS value 
FROM chunks_turn ct 
JOIN transcripts t ON ct.transcript_id = t.id 
WHERE (ct.speaker = $5::text OR ct.speaker = (
    SELECT speaker FROM chunks_turn ct2 
    JOIN transcripts t2 ON ct2.transcript_id = t2.id 
    WHERE ct2.text ILIKE '%' || $5::text || '%' 
    AND ($1::uuid IS NULL OR t2.user_id = $1::uuid) 
    AND ($2::date IS NULL OR t2.meeting_date >= $2::date) 
    AND ($3::date IS NULL OR t2.meeting_date <= $3::date) 
    LIMIT 1
)) 
AND {where_clause}
```

### B. Số lượt phát biểu (`target="turn_count"`)
Đếm số lần một người lên tiếng. Sử dụng logic tìm speaker tương tự `speaking_time` nhưng phần SELECT là:
`SELECT COUNT(*)::float AS value`

### C. Số lần đề cập từ khóa (`target="mention_count"`)
Đếm số lần một từ khóa ($6) xuất hiện trong văn bản.

**Định dạng:**
```sql
SELECT COALESCE(SUM(
    CASE WHEN $6::text IS NULL OR $6::text = '' THEN 0 
    ELSE (LENGTH(ct.text) - LENGTH(REPLACE(ct.text, $6::text, ''))) / LENGTH($6::text) 
    END
), 0)::float AS value 
FROM chunks_turn ct 
JOIN transcripts t ON ct.transcript_id = t.id 
WHERE {where_clause}
```

### D. Tìm cuộc họp dài nhất/ngắn nhất (`target="duration_seconds"` + `operator="max|min"`)
Truy vấn này trả về thông tin chi tiết của 1 cuộc họp.

**Định dạng:**
```sql
SELECT t.id::text AS transcript_id, t.session_id AS session_id, 
       t.meeting_date::text AS meeting_date, t.participants AS participants, 
       t.duration_seconds AS value, t.summary AS summary 
FROM transcripts t 
WHERE {where_clause} AND t.duration_seconds IS NOT NULL 
ORDER BY t.duration_seconds {DESC|ASC}, t.meeting_date {DESC|ASC} LIMIT 1
```

---

## 3. Truy vấn hỗ trợ Phân nhóm (Group By)

Dành cho `target="meeting_count"` hoặc `"duration_seconds"` (với operator `sum` hoặc `avg`).

### Định nghĩa biểu thức giá trị (`value_expr`):
- **Meeting Count:** `COUNT(DISTINCT t.id)`
- **Duration Seconds (Sum):** `COALESCE(SUM(t.duration_seconds), 0)`
- **Duration Seconds (Avg):** `COALESCE(AVG(t.duration_seconds), 0)`

### Phân nhóm theo Người dùng (`group_by="user_id"`)
```sql
SELECT t.user_id::text AS group_key, {value_expr} AS value 
FROM transcripts t WHERE {where_clause} 
GROUP BY t.user_id ORDER BY value DESC LIMIT 20
```

### Phân nhóm theo Ngày (`group_by="day"`)
```sql
SELECT t.meeting_date::text AS group_key, {value_expr} AS value 
FROM transcripts t WHERE {where_clause} 
GROUP BY t.meeting_date ORDER BY group_key LIMIT 31
```

### Phân nhóm theo Người nói (`group_by="speaker"`)
```sql
SELECT x.speaker AS group_key, {value_expr} AS value 
FROM transcripts t 
JOIN (SELECT DISTINCT transcript_id, speaker FROM chunks_turn) x ON x.transcript_id = t.id 
WHERE {where_clause} 
GROUP BY x.speaker ORDER BY value DESC LIMIT 20
```

### Không phân nhóm (Scalar fallback)
```sql
SELECT {value_expr} AS value FROM transcripts t WHERE {where_clause}
```

---

## 4. Danh sách tham số (Parameters)

| Tham số | Kiểu dữ liệu | Mô tả |
| :--- | :--- | :--- |
| `$1` | UUID | ID của người dùng (bắt buộc để đảm bảo quyền truy cập) |
| `$2` | Date | Ngày bắt đầu lọc |
| `$3` | Date | Ngày kết thúc lọc |
| `$4` | Text | Từ khóa lọc ngữ cảnh (ILIKE trên summary/raw_text) |
| `$5` | Text | Tên người nói hoặc từ khóa để tìm định danh người nói |
| `$6` | Text | Từ khóa cần đếm số lần đề cập |
