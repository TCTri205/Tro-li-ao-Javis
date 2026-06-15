# SQL Formats and Query Patterns

This document describes the database schema, data formats, and SQL query patterns used by the Numeric SQL Tool.

## 1. Schema Overview

The database follows a relational structure optimized for meeting transcripts and document analysis.

### Core Tables

- `transcripts`: Stores high-level meeting metadata and raw text.
- `chunks_passage`: (Optional) Semantic passages derived from transcripts.
- `chunks_turn`: Individual speaker utterances with timestamps.
- `company_documents`: Metadata for uploaded PDF/Word documents.
- `company_chunks`: Text chunks from documents.
- `chat_conversations` & `chat_messages`: Interaction history.

---

## 2. Table Definitions

### `public.transcripts`

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | `uuid` | Primary Key. |
| `session_id` | `varchar(64)` | Unique identifier for the meeting session. |
| `user_id` | `uuid` | Owner of the transcript. |
| `meeting_date` | `date` | Date the meeting took place. |
| `participants` | `jsonb` | List of speaker names/labels. |
| `speaker_count` | `integer` | Number of distinct speakers. |
| `duration_seconds` | `integer` | Total duration of the meeting. |
| `raw_text` | `text` | The full concatenated transcript. |
| `summary` | `text` | AI-generated summary. |
| `project_id` | `uuid` | Organization/Project scope identifier. |

### `public.chunks_turn`

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | `uuid` | Primary Key. |
| `transcript_id` | `uuid` | FK to `transcripts.id`. |
| `turn_index` | `integer` | Sequence number of the turn. |
| `speaker` | `varchar(32)` | Speaker label (e.g., "SPEAKER 1"). |
| `time_start_sec` | `integer` | Start offset in seconds. |
| `time_end_sec` | `integer` | End offset in seconds. |
| `text` | `text` | Utterance content. |
| `chunk_metadata` | `jsonb` | Additional AI-extracted fields (entities, importance). |

---

## 3. Standard Query Parameters

The tool uses `asyncpg` with numbered placeholders ($1 to $4) for security and performance.

| Parameter | Type | Mapping |
| :--- | :--- | :--- |
| `$1` | `uuid` | `user_id` (Filtered by default). |
| `$2` | `date` | `date_start` (Lower bound). |
| `$3` | `date` | `date_end` (Upper bound). |
| `$4` | `text` | `context_filter` (ILKE search on summary/text). |

---

## 4. SQL Query Patterns

### Standard WHERE Clause

```sql
WHERE ($1::uuid IS NULL OR t.user_id = $1::uuid)
  AND ($2::date IS NULL OR t.meeting_date >= $2::date)
  AND ($3::date IS NULL OR t.meeting_date <= $3::date)
  AND ($4::text IS NULL OR t.summary ILIKE '%' || $4 || '%' OR t.raw_text ILIKE '%' || $4 || '%')
```

### 1. Meeting Aggregates (transcripts table)

- **Total Duration**: `SELECT SUM(t.duration_seconds) FROM transcripts t WHERE ...`
- **Meeting Count**: `SELECT COUNT(DISTINCT t.id) FROM transcripts t WHERE ...`
- **Longest Meeting**:
  ```sql
  SELECT t.duration_seconds AS value, t.summary, ...
  FROM transcripts t
  WHERE ...
  ORDER BY t.duration_seconds DESC LIMIT 1
  ```

### 2. Turn-level Aggregates (chunks_turn table)

- **Average Turn Duration**:
  ```sql
  SELECT AVG(ct.time_end_sec - ct.time_start_sec) AS value
  FROM chunks_turn ct
  JOIN transcripts t ON t.id = ct.transcript_id
  WHERE ...
  ```
- **Turn Count by Speaker**:
  ```sql
  SELECT COUNT(*) AS value
  FROM chunks_turn ct
  JOIN transcripts t ON t.id = ct.transcript_id
  WHERE ... AND ct.speaker = 'SPEAKER 1'
  ```

### 3. Entity Mention Counting

```sql
SELECT COUNT(*) AS value
FROM chunks_turn ct
JOIN transcripts t ON t.id = ct.transcript_id
WHERE ... AND ct.text ILIKE '%梅田%'
```

### 4. Speaker Identification (Most/Least Talkative)

- **Most talkative (by number of turns)**:
  ```sql
  SELECT ct.speaker AS value, COUNT(*) AS turn_count
  FROM chunks_turn ct
  JOIN transcripts t ON t.id = ct.transcript_id
  WHERE ...
  GROUP BY ct.speaker
  ORDER BY turn_count DESC LIMIT 1
  ```

- **Speaker with longest single turn**:
  ```sql
  SELECT ct.speaker AS value, MAX(ct.time_end_sec - ct.time_start_sec) AS duration
  FROM chunks_turn ct
  JOIN transcripts t ON t.id = ct.transcript_id
  WHERE ...
  GROUP BY ct.speaker
  ORDER BY duration DESC LIMIT 1
  ```

---

## 5. Advanced Grouping Patterns

### Meeting-level Aggregates by Speaker
To aggregate meeting data (like duration) by speaker, the tool joins transcripts with a unique set of speakers per meeting:

```sql
SELECT x.speaker AS group_key, SUM(t.duration_seconds) AS value
FROM transcripts t
JOIN (SELECT DISTINCT transcript_id, speaker FROM chunks_turn) x ON x.transcript_id = t.id
WHERE ...
GROUP BY x.speaker
ORDER BY value DESC LIMIT 20
```

### Temporal and User Grouping

- **By Day**:
  ```sql
  SELECT t.meeting_date::text AS group_key, COUNT(DISTINCT t.id) AS value
  FROM transcripts t
  WHERE ...
  GROUP BY t.meeting_date
  ORDER BY group_key LIMIT 31
  ```

- **By User**:
  ```sql
  SELECT t.user_id::text AS group_key, SUM(t.duration_seconds) AS value
  FROM transcripts t
  WHERE ...
  GROUP BY t.user_id
  ORDER BY value DESC LIMIT 20
  ```

---

## 6. JSON Formats

### `participants` (transcripts)
```json
["SPEAKER 1", "SPEAKER 2"]
```

### `chunk_metadata` (chunks_turn)
```json
{
  "topics": ["call"],
  "entities": ["梅田"],
  "turn_types": ["update"],
  "importance_score": 3
}
```

---

## 7. Performance & Indices

The schema includes several indices to optimize aggregation and filtering.

- **JSONB Search**: `GIN` indexes are used on `chunk_metadata` columns for fast topic/entity lookups.
- **Meeting Filtering**: Multiple `BTREE` indexes cover `(user_id, meeting_date)` and `(project_id, meeting_date)` to speed up date-range queries.
- **Partial Indexing**: `ix_transcripts_sync` is a partial index targeting unsynced rows (`WHERE qdrant_synced = false`), optimizing background synchronization tasks.

---

## 8. Metadata in Results

For certain queries, the tool returns additional context in the `metadata` field of the result rows.

- **Extreme Duration (Longest/Shortest Meeting)**: Returns `transcript_id`, `session_id`, `meeting_date`, `participants`, and `summary`.
- **Speaker Identification**: Returns the identified speaker's name in the `speaker` field and the raw row data in `raw`.
- **Empty Results**: May return `{"no_data": true}` if no matches are found for an extreme-value query.

---

## 9. Data Loading Sequence

When restoring or initializing data, files must be applied in the following order to satisfy Foreign Key constraints:

1. `transcripts.sql`
2. `chunks_passage.sql`
3. `chunks_turn.sql`
4. `company_documents.sql`
5. `company_chunks.sql`
