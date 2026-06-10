import pandas as pd
import re

def fix_sql(question, sql):
    if sql == '"SKIP (operator=skip, target=none)"' or sql == 'SKIP (operator=skip, target=none)':
        return sql
    
    # Common where clause template
    where_clause = "($1::uuid IS NULL OR t.user_id = $1::uuid) AND ($2::date IS NULL OR t.meeting_date >= $2::date) AND ($3::date IS NULL OR t.meeting_date <= $3::date) AND ($4::text IS NULL OR t.summary ILIKE '%' || $4 || '%' OR t.raw_text ILIKE '%' || $4 || '%') AND ($5::text IS NULL OR TRUE) AND ($6::text IS NULL OR TRUE)"
    
    # 1. Who spoke the most (最も多く発言)
    if "最も多く発言" in question:
        # We assume "spoke the most" means count of turns by default, or could be duration.
        # Let's check existing SQL to see if it was trying duration or count.
        # If it was using SUM(t.duration_seconds), it's duration-oriented.
        return f"SELECT ct.speaker AS group_key, SUM(ct.time_end_sec - ct.time_start_sec)::float AS value FROM chunks_turn ct JOIN transcripts t ON ct.transcript_id = t.id WHERE {where_clause} GROUP BY ct.speaker ORDER BY value DESC LIMIT 20"

    # 2. Longest statement (最も長い発言)
    if "最も長い発言" in question:
        return f"SELECT ct.speaker AS speaker, (ct.time_end_sec - ct.time_start_sec)::float AS value, ct.text FROM chunks_turn ct JOIN transcripts t ON ct.transcript_id = t.id WHERE {where_clause} ORDER BY value DESC LIMIT 1"

    # 3. Shortest statement (最も短い発言)
    if "最も短い発言" in question:
        return f"SELECT ct.speaker AS speaker, (ct.time_end_sec - ct.time_start_sec)::float AS value, ct.text FROM chunks_turn ct JOIN transcripts t ON ct.transcript_id = t.id WHERE {where_clause} ORDER BY value ASC LIMIT 1"

    # 4. Total call duration (総通話時間 / 通話時間はどのくらい)
    if "総通話時間" in question or "通話時間はどのくらい" in question:
        return f"SELECT COALESCE(SUM(t.duration_seconds), 0)::float AS value FROM transcripts t WHERE {where_clause}"

    # 5. Average speaking time for a speaker (平均発話時間)
    if "平均発話時間" in question:
        # We need the speaker subquery logic from sql_formats.md
        speaker_subquery = "(ct.speaker = $5::text OR ct.speaker = (SELECT speaker FROM chunks_turn ct2 JOIN transcripts t2 ON ct2.transcript_id = t2.id WHERE ct2.text ILIKE '%' || $5::text || '%' AND ($1::uuid IS NULL OR t2.user_id = $1::uuid) AND ($2::date IS NULL OR t2.meeting_date >= $2::date) AND ($3::date IS NULL OR t2.meeting_date <= $3::date) LIMIT 1))"
        return f"SELECT COALESCE(AVG(ct.time_end_sec - ct.time_start_sec), 0)::float AS value FROM chunks_turn ct JOIN transcripts t ON ct.transcript_id = t.id WHERE {speaker_subquery} AND {where_clause}"

    # 6. How many times did speaker X speak (何回発言)
    if "何回発言" in question:
        speaker_subquery = "(ct.speaker = $5::text OR ct.speaker = (SELECT speaker FROM chunks_turn ct2 JOIN transcripts t2 ON ct2.transcript_id = t2.id WHERE ct2.text ILIKE '%' || $5::text || '%' AND ($1::uuid IS NULL OR t2.user_id = $1::uuid) AND ($2::date IS NULL OR t2.meeting_date >= $2::date) AND ($3::date IS NULL OR t2.meeting_date <= $3::date) LIMIT 1))"
        return f"SELECT COUNT(*)::float AS value FROM chunks_turn ct JOIN transcripts t ON ct.transcript_id = t.id WHERE {speaker_subquery} AND {where_clause}"

    # 7. Mention count (何回言及)
    if "何回言及" in question:
        mention_expr = "COALESCE(SUM(CASE WHEN $6::text IS NULL OR $6::text = '' THEN 0 ELSE (LENGTH(ct.text) - LENGTH(REPLACE(ct.text, $6::text, ''))) / NULLIF(LENGTH($6::text), 0) END), 0)::float"
        return f"SELECT {mention_expr} AS value FROM chunks_turn ct JOIN transcripts t ON ct.transcript_id = t.id WHERE {where_clause}"

    # 8. Meeting count (通話履歴...あったか / 履歴を表示)
    if "通話履歴" in question or "話題は出ましたか" in question or "通話はありましたか" in question:
        return f"SELECT COUNT(DISTINCT t.id)::float AS value FROM transcripts t WHERE {where_clause}"

    return sql

# Load CSV
df = pd.read_csv('d:/VJ/Tro-li-ao-Javis/numeric_sql_tool/eval_v2/questions_GTqueries.csv')
df['SQL'] = df.apply(lambda row: fix_sql(row['question'], row['SQL']), axis=1)

# Save fixed version
df.to_csv('d:/VJ/Tro-li-ao-Javis/numeric_sql_tool/eval_v2/questions_GTqueries_fixed.csv', index=False)
print("Done fixing GT queries.")
