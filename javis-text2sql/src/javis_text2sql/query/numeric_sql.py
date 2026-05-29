from __future__ import annotations

import logging
import re
import calendar
from datetime import date, timedelta
from typing import Literal, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Keywords BẮT BUỘC phải có ÍT NHẤT MỘT cái để được intercept:
_MEETING_CONTEXT_SIGNALS = re.compile(
    r"会議|ミーティング|打ち合わせ|合計時間|所要時間|会議時間|mtg|"
    r"最も長かった|一番長い|最長の|最も短かった|一番短い|最短の"
)

# Keywords mà khi có thì TUYỆT ĐỐI KHÔNG intercept (thuộc về views khác hoặc dạng list/detail):
_NON_MEETING_SIGNALS = re.compile(
    r"コミットメント|タスク|アクションアイテム|質問|金額|予算|"
    r"トピック|エンティティ|発言|感情|日付|担当|期限|budget|amount|"
    r"一覧|リスト|詳細|内容|アジェンダ|議事録"
)

_TIMESTAMP_RE = re.compile(r"何分頃|何秒頃|いつ.*(発言|言)|何時.*(発言|言)")

_DURATION_MAX_RE = re.compile(r"最も長|一番長|最長|最大.*(会議|ミーティング|打ち合わせ|時間|mtg)")
_DURATION_MIN_RE = re.compile(r"最も短|一番短|最短|最小.*(会議|ミーティング|打ち合わせ|時間|mtg)")


class NumericIntent(BaseModel):
    operator: Literal["sum", "avg", "max", "min", "count", "skip"] = "sum"
    target: Literal["duration_seconds", "meeting_count", "none"] = "meeting_count"
    group_by: Literal["none", "day", "speaker"] = "none"
    date_start: date | None = None
    date_end: date | None = None


class NumericRow(BaseModel):
    group_key: str | None = None
    value: float
    metadata: dict = {}


class NumericResult(BaseModel):
    operator: str
    target: str
    rows: list[NumericRow] = []
    source_meeting_ids: list[str] = []
    sql_used: str = ""
    metadata: dict = {}


def resolve_relative_date(query: str, ref_date: date) -> tuple[date | None, date | None]:
    q = query

    if "先週" in q:
        weekday = ref_date.weekday()
        this_week_start = ref_date - timedelta(days=weekday)
        last_week_start = this_week_start - timedelta(days=7)
        last_week_end = last_week_start + timedelta(days=6)
        return last_week_start, last_week_end

    if "今週" in q:
        weekday = ref_date.weekday()
        this_week_start = ref_date - timedelta(days=weekday)
        this_week_end = this_week_start + timedelta(days=6)
        return this_week_start, this_week_end

    if "先月" in q:
        if ref_date.month == 1:
            last_month_start = date(ref_date.year - 1, 12, 1)
        else:
            last_month_start = date(ref_date.year, ref_date.month - 1, 1)
        _, last_last_day = calendar.monthrange(last_month_start.year, last_month_start.month)
        last_month_end = date(last_month_start.year, last_month_start.month, last_last_day)
        return last_month_start, last_month_end

    if "今月" in q:
        this_month_start = date(ref_date.year, ref_date.month, 1)
        _, last_day = calendar.monthrange(ref_date.year, ref_date.month)
        this_month_end = date(ref_date.year, ref_date.month, last_day)
        return this_month_start, this_month_end

    if "昨日" in q:
        yesterday = ref_date - timedelta(days=1)
        return yesterday, yesterday

    if "今日" in q:
        return ref_date, ref_date

    if "明日" in q:
        tomorrow = ref_date + timedelta(days=1)
        return tomorrow, tomorrow

    match = re.search(r"(\d{1,2})\s*月", q)
    if match:
        m = int(match.group(1))
        if 1 <= m <= 12:
            year = ref_date.year
            start_d = date(year, m, 1)
            _, last_day = calendar.monthrange(year, m)
            end_d = date(year, m, last_day)
            return start_d, end_d

    return None, None


def heuristic_numeric_intent(query: str, ref_date: date) -> NumericIntent:
    # Gate 1: Skip nếu có non-meeting signal
    if _NON_MEETING_SIGNALS.search(query):
        return NumericIntent(operator="skip", target="none")

    # Gate 2: Skip nếu KHÔNG có meeting context signal
    if not _MEETING_CONTEXT_SIGNALS.search(query):
        return NumericIntent(operator="skip", target="none")

    # Gate 3: Skip nếu là timestamp query
    if _TIMESTAMP_RE.search(query):
        return NumericIntent(operator="skip", target="none")

    operator = "sum"
    if _DURATION_MAX_RE.search(query) or "最も長かった" in query or "一番長い" in query or "最長の" in query:
        operator = "max"
    elif _DURATION_MIN_RE.search(query) or "最も短かった" in query or "一番短い" in query or "最短の" in query:
        operator = "min"
    elif re.search(r"平均", query):
        operator = "avg"
    elif re.search(r"最大|一番多", query):
        operator = "max"
    elif re.search(r"最小|一番少", query):
        operator = "min"
    elif re.search(r"何件|何回|件数|会議数", query):
        operator = "count"

    target = "meeting_count"
    if operator in {"max", "min"}:
        target = "duration_seconds"
    elif re.search(r"何時間|所要時間|会議時間|合計時間", query):
        target = "duration_seconds"
    elif re.search(r"何件|会議数|会議件数", query) or re.search(r"ミーティングは何件|会議はありましたか|会議は何件", query):
        target = "meeting_count"
        operator = "count"

    group_by = "none"
    if re.search(r"日ごと|日別", query):
        group_by = "day"
    elif re.search(r"話者ごと|話者別|話者ごとの|スピーカーごと", query):
        group_by = "speaker"

    date_start, date_end = resolve_relative_date(query, ref_date)

    return NumericIntent(
        operator=operator,
        target=target,
        group_by=group_by,
        date_start=date_start,
        date_end=date_end
    )


async def _execute_numeric_readonly(
    conn: Any,
    sql: str,
    params: tuple,
    user_id: str,
    statement_timeout_ms: int = 5000,
) -> list[dict[str, Any]]:
    async with conn.transaction():
        await conn.execute("SET TRANSACTION READ ONLY")
        await conn.execute(f"SET LOCAL statement_timeout = {int(statement_timeout_ms)}")
        await conn.execute(
            "SELECT set_config('app.current_user_id', $1, true)", str(user_id)
        )
        rows = await conn.fetch(sql, *params)
    return [dict(row) for row in rows]


async def _run_duration_extreme(
    conn: Any,
    intent: NumericIntent,
    user_id: str,
    statement_timeout_ms: int,
) -> NumericResult:
    direction = "DESC" if intent.operator == "max" else "ASC"
    sql = f"""SELECT
    m.id::text AS meeting_id,
    m.title,
    m.meeting_date::text AS meeting_date,
    m.duration_seconds AS value,
    m.summary,
    (SELECT ARRAY_AGG(DISTINCT t.speaker) FROM turns t WHERE t.meeting_id = m.id) AS participants
FROM meetings m
WHERE m.user_id = $1::uuid
  AND ($2::date IS NULL OR m.meeting_date >= $2)
  AND ($3::date IS NULL OR m.meeting_date <= $3)
  AND m.duration_seconds IS NOT NULL
ORDER BY m.duration_seconds {direction}, m.meeting_date {direction}
LIMIT 1"""
    params = (user_id, intent.date_start, intent.date_end)
    rows = await _execute_numeric_readonly(conn, sql, params, user_id, statement_timeout_ms)
    if not rows:
        return NumericResult(
            operator=intent.operator,
            target=intent.target,
            rows=[NumericRow(value=0.0, metadata={"no_data": True})],
            sql_used=sql,
        )
    row = rows[0]
    meeting_id = row["meeting_id"]
    metadata = {
        "meeting_id": meeting_id,
        "title": row["title"],
        "meeting_date": row["meeting_date"],
        "participants": row["participants"] or [],
        "summary": row["summary"],
    }
    return NumericResult(
        operator=intent.operator,
        target=intent.target,
        rows=[NumericRow(value=float(row["value"] or 0), metadata=metadata)],
        source_meeting_ids=[meeting_id],
        sql_used=sql,
    )


async def run_numeric_sql(
    conn: Any,
    intent: NumericIntent,
    user_id: str,
    statement_timeout_ms: int = 5000,
) -> NumericResult:
    if intent.operator in {"skip", "none"} or intent.target in {"none"}:
        return NumericResult(operator="skip", target="none", metadata={"skipped": True})

    if intent.target == "duration_seconds" and intent.operator in {"max", "min"}:
        return await _run_duration_extreme(conn, intent, user_id, statement_timeout_ms)

    params = (user_id, intent.date_start, intent.date_end)

    agg_funcs = {"sum": "SUM", "avg": "AVG", "max": "MAX", "min": "MIN", "count": "COUNT"}
    agg = agg_funcs.get(intent.operator, "SUM")

    if intent.target == "meeting_count":
        value_expr = "COUNT(DISTINCT m.id)"
    else:
        if intent.operator == "avg":
            value_expr = "COALESCE(AVG(m.duration_seconds), 0.0)"
        else:
            value_expr = f"COALESCE({agg}(m.duration_seconds), 0)"

    where = (
        "m.user_id = $1::uuid "
        "AND ($2::date IS NULL OR m.meeting_date >= $2) "
        "AND ($3::date IS NULL OR m.meeting_date <= $3)"
    )

    if intent.group_by == "day":
        sql = f"""SELECT m.meeting_date::text AS group_key, {value_expr} AS value
FROM meetings m
WHERE {where}
GROUP BY m.meeting_date
ORDER BY group_key
LIMIT 31"""
        rows = await _execute_numeric_readonly(conn, sql, params, user_id, statement_timeout_ms)
        numeric_rows = [NumericRow(group_key=r["group_key"], value=float(r["value"] or 0)) for r in rows]
    elif intent.group_by == "speaker":
        sql = f"""SELECT x.speaker AS group_key, {value_expr} AS value
FROM meetings m
JOIN (SELECT DISTINCT meeting_id, speaker FROM turns) x ON x.meeting_id = m.id
WHERE {where}
GROUP BY x.speaker
ORDER BY value DESC
LIMIT 20"""
        rows = await _execute_numeric_readonly(conn, sql, params, user_id, statement_timeout_ms)
        numeric_rows = [NumericRow(group_key=r["group_key"], value=float(r["value"] or 0)) for r in rows]
    else:
        sql = f"SELECT {value_expr} AS value FROM meetings m WHERE {where}"
        rows = await _execute_numeric_readonly(conn, sql, params, user_id, statement_timeout_ms)
        val = rows[0]["value"] if rows else 0
        numeric_rows = [NumericRow(value=float(val or 0))]

    if intent.group_by != "none" and not numeric_rows:
        numeric_rows = [NumericRow(group_key="該当なし", value=0.0)]

    # Fetch source meeting IDs for traceability
    ids_sql = f"SELECT m.id::text AS meeting_id FROM meetings m WHERE {where}"
    ids_rows = await _execute_numeric_readonly(conn, ids_sql, params, user_id, statement_timeout_ms)
    source_meeting_ids = [r["meeting_id"] for r in ids_rows]

    return NumericResult(
        operator="count" if intent.target == "meeting_count" else intent.operator,
        target=intent.target,
        rows=numeric_rows,
        source_meeting_ids=source_meeting_ids,
        sql_used=sql,
        metadata={
            "date_start": intent.date_start.isoformat() if intent.date_start else None,
            "date_end": intent.date_end.isoformat() if intent.date_end else None,
        }
    )
