import re
import csv
import os

def get_sql(intent):
    where_clause = (
        "($1::uuid IS NULL OR t.user_id = $1::uuid) "
        "AND ($2::date IS NULL OR t.meeting_date >= $2::date) "
        "AND ($3::date IS NULL OR t.meeting_date <= $3::date) "
        "AND ($4::text IS NULL OR t.summary ILIKE '%' || $4 || '%' OR t.raw_text ILIKE '%' || $4 || '%') "
        "AND ($5::text IS NULL OR TRUE) "
        "AND ($6::text IS NULL OR TRUE)"
    )

    target = intent.get('target')
    operator = intent.get('operator')
    group_by = intent.get('group_by', 'none')
    
    if operator == 'skip':
        return 'SKIP (operator=skip, target=none)'

    if target == 'speaking_time':
        agg = "AVG" if operator == 'avg' else "SUM"
        return (
            f"SELECT COALESCE({agg}(ct.time_end_sec - ct.time_start_sec), 0)::float AS value "
            "FROM chunks_turn ct "
            "JOIN transcripts t ON ct.transcript_id = t.id "
            "WHERE (ct.speaker = $5::text OR ct.speaker = ("
            "SELECT speaker FROM chunks_turn ct2 "
            "JOIN transcripts t2 ON ct2.transcript_id = t2.id "
            "WHERE ct2.text ILIKE '%' || $5::text || '%' "
            "AND ($1::uuid IS NULL OR t2.user_id = $1::uuid) "
            "AND ($2::date IS NULL OR t2.meeting_date >= $2::date) "
            "AND ($3::date IS NULL OR t2.meeting_date <= $3::date) "
            "LIMIT 1"
            ")) "
            f"AND {where_clause}"
        )

    if target == 'turn_count':
        return (
            "SELECT COUNT(*)::float AS value "
            "FROM chunks_turn ct "
            "JOIN transcripts t ON ct.transcript_id = t.id "
            "WHERE (ct.speaker = $5::text OR ct.speaker = ("
            "SELECT speaker FROM chunks_turn ct2 "
            "JOIN transcripts t2 ON ct2.transcript_id = t2.id "
            "WHERE ct2.text ILIKE '%' || $5::text || '%' "
            "AND ($1::uuid IS NULL OR t2.user_id = $1::uuid) "
            "AND ($2::date IS NULL OR t2.meeting_date >= $2::date) "
            "AND ($3::date IS NULL OR t2.meeting_date <= $3::date) "
            "LIMIT 1"
            ")) "
            f"AND {where_clause}"
        )

    if target == 'mention_count':
        return (
            "SELECT COALESCE(SUM("
            "CASE WHEN $6::text IS NULL OR $6::text = '' THEN 0 "
            "ELSE (LENGTH(ct.text) - LENGTH(REPLACE(ct.text, $6::text, ''))) / LENGTH($6::text) "
            "END"
            "), 0)::float AS value "
            "FROM chunks_turn ct "
            "JOIN transcripts t ON ct.transcript_id = t.id "
            f"WHERE {where_clause}"
        )

    if target == 'meeting_count':
        value_expr = "COUNT(DISTINCT t.id)"
    elif target == 'duration_seconds' and operator in {'max', 'min'}:
        direction = "DESC" if operator == 'max' else "ASC"
        return (
            "SELECT t.id::text AS transcript_id, t.session_id AS session_id, "
            "t.meeting_date::text AS meeting_date, t.participants AS participants, "
            "t.duration_seconds AS value, t.summary AS summary "
            "FROM transcripts t WHERE "
            f"{where_clause} AND t.duration_seconds IS NOT NULL "
            f"ORDER BY t.duration_seconds {direction}, t.meeting_date {direction} LIMIT 1"
        )
    else:
        agg = "AVG" if operator == 'avg' else "SUM"
        value_expr = f"COALESCE({agg}(t.duration_seconds), 0)"

    if group_by == 'user_id':
        return (
            "SELECT t.user_id::text AS group_key, "
            f"{value_expr} AS value "
            "FROM transcripts t WHERE "
            f"{where_clause} GROUP BY t.user_id ORDER BY value DESC LIMIT 20"
        )
    if group_by == 'day':
        return (
            "SELECT t.meeting_date::text AS group_key, "
            f"{value_expr} AS value "
            "FROM transcripts t WHERE "
            f"{where_clause} GROUP BY t.meeting_date ORDER BY group_key LIMIT 31"
        )
    if group_by == 'speaker':
        return (
            "SELECT x.speaker AS group_key, "
            f"{value_expr} AS value "
            "FROM transcripts t "
            "JOIN (SELECT DISTINCT transcript_id, speaker FROM chunks_turn) x ON x.transcript_id = t.id "
            "WHERE "
            f"{where_clause} GROUP BY x.speaker ORDER BY value DESC LIMIT 20"
        )
    
    return f"SELECT {value_expr} AS value FROM transcripts t WHERE {where_clause}"

def parse_question(q):
    q = q.strip()
    intent = {'operator': 'skip', 'target': 'none', 'group_by': 'none'}
    
    # Simple keyword based mapping
    if '何回言及' in q or '言及されましたか' in q:
        intent['target'] = 'mention_count'
        intent['operator'] = 'sum'
    elif '通話時間はどのくらい' in q or '総通話時間' in q:
        intent['target'] = 'duration_seconds'
        intent['operator'] = 'sum'
    elif '平均発話時間' in q:
        intent['target'] = 'speaking_time'
        intent['operator'] = 'avg'
    elif '何回発言' in q:
        intent['target'] = 'turn_count'
        intent['operator'] = 'count'
    elif '最も多く発言したのは誰' in q or '最も多く発言したのは' in q:
        intent['target'] = 'duration_seconds'
        intent['operator'] = 'sum'
        intent['group_by'] = 'speaker'
    elif '最も長い' in q and ('電話' in q or '通話' in q or '会議' in q):
        intent['target'] = 'duration_seconds'
        intent['operator'] = 'max'
    elif '最も短い' in q and ('電話' in q or '通話' in q or '会議' in q):
        intent['target'] = 'duration_seconds'
        intent['operator'] = 'min'
    elif '何件' in q or '何回' in q or '履歴' in q or '通話はありましたか' in q or '話題は出ましたか' in q or '連絡はありましたか' in q:
        intent['target'] = 'meeting_count'
        intent['operator'] = 'count'
    elif '日ごとの' in q or '毎日' in q:
        intent['target'] = 'meeting_count'
        intent['operator'] = 'count'
        intent['group_by'] = 'day'
    
    return intent

with open('d:/VJ/Tro-li-ao-Javis/numeric_sql_tool/eval_v2/queries.txt', 'r', encoding='utf-8') as f:
    queries = f.readlines()

output_path = 'd:/VJ/Tro-li-ao-Javis/numeric_sql_tool/questions_GTqueries.csv'
with open(output_path, 'w', encoding='utf-8', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['question', 'SQL'])
    for q in queries:
        q = q.strip()
        if not q: continue
        intent = parse_question(q)
        sql = get_sql(intent)
        writer.writerow([q, sql])

print(f"Generated {output_path}")
