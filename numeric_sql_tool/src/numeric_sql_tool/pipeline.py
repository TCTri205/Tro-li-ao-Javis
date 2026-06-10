from __future__ import annotations

import logging
from datetime import date
from typing import Any

from .heuristics import enforce_intent_invariants, heuristic_numeric_intent, resolve_date_range
from .llm_client import LLMClient
from .models import NumericIntent, NumericResult, NumericRow
from .prompt import build_numeric_intent_prompt

logger = logging.getLogger(__name__)


async def extract_numeric_intent(question: str, llm_client: LLMClient | None = None) -> NumericIntent:
    fallback = heuristic_numeric_intent(question)
    fallback = enforce_intent_invariants(fallback, question)
    if llm_client is None:
        return fallback

    try:
        system, user = build_numeric_intent_prompt(question)
        result = await llm_client.structured_output(system=system, user=user, schema=NumericIntent)
        if result.operator == "none":
            result.operator = "skip"
        if result == NumericIntent():
            return fallback
        if result.operator == "skip" or result.target in {"none", "time_start_sec"}:
            return enforce_intent_invariants(result, question)
        if fallback.operator != "sum" and result.operator == "sum":
            result.operator = fallback.operator
        if fallback.target != "meeting_count" and result.target == "meeting_count":
            result.target = fallback.target
        if fallback.group_by != "none" and result.group_by == "none":
            result.group_by = fallback.group_by
        if result.context_filter is None:
            result.context_filter = fallback.context_filter
        
        result = enforce_intent_invariants(result, question)
        return result
    except Exception as exc:
        logger.warning("numeric intent extraction failed: %s", exc)
        return fallback



async def run_numeric_pipeline(
    question: str,
    db_pool: Any,
    llm_client: LLMClient | None,
    user_id: str,
    reference_date: date,
    *,
    date_start: date | None = None,
    date_end: date | None = None,
    allow_cross_user: bool = False,
    statement_timeout_ms: int = 5000,
) -> NumericResult:
    intent = await extract_numeric_intent(question, llm_client=llm_client)

    if intent.operator in {"skip", "none"} or intent.target in {"none", "time_start_sec"}:
        return NumericResult(operator="skip", target="none", metadata={"skipped": True, "sql": None})

    if intent.group_by == "user_id" and not allow_cross_user:
        return NumericResult(
            operator="skip",
            target="none",
            metadata={"skipped": True, "error": "cross-user aggregate not allowed", "sql": None},
        )

    if date_start is None and date_end is None:
        date_start, date_end = resolve_date_range(question, reference_date)

    params = [user_id, date_start, date_end, intent.context_filter, intent.speaker, intent.keyword]

    async with db_pool.acquire() as conn:
        rows, sql_used = await _run_numeric_query(
            conn,
            intent,
            params,
            user_id=user_id,
            statement_timeout_ms=statement_timeout_ms,
        )

    result = NumericResult(operator=intent.operator, target=intent.target, rows=rows)
    result.metadata.update(
        {
            "date_start": date_start.isoformat() if date_start else None,
            "date_end": date_end.isoformat() if date_end else None,
            "group_by": intent.group_by,
            "sql": sql_used,
        }
    )
    return result


def _numeric_where_clause() -> str:
    return (
        "($1::uuid IS NULL OR t.user_id = $1::uuid) "
        "AND ($2::date IS NULL OR t.meeting_date >= $2::date) "
        "AND ($3::date IS NULL OR t.meeting_date <= $3::date) "
        "AND ($4::text IS NULL OR t.summary ILIKE '%' || $4 || '%' OR t.raw_text ILIKE '%' || $4 || '%') "
        "AND ($5::text IS NULL OR TRUE) "
        "AND ($6::text IS NULL OR TRUE)"
    )


def build_numeric_sql(intent: NumericIntent) -> str | None:
    """Return the SQL that run_numeric_pipeline would execute (params $1..$4)."""
    if intent.operator in {"skip", "none"} or intent.target in {"none", "time_start_sec"}:
        return None

    where = _numeric_where_clause()

    if intent.target == "speaking_time":
        agg = "AVG" if intent.operator == "avg" else "SUM"
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
            f"AND {where}"
        )

    if intent.target == "turn_count":
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
            f"AND {where}"
        )

    if intent.target == "mention_count":
        return (
            "SELECT COALESCE(SUM("
            "CASE WHEN $6::text IS NULL OR $6::text = '' THEN 0 "
            "ELSE (LENGTH(ct.text) - LENGTH(REPLACE(ct.text, $6::text, ''))) / LENGTH($6::text) "
            "END"
            "), 0)::float AS value "
            "FROM chunks_turn ct "
            "JOIN transcripts t ON ct.transcript_id = t.id "
            f"WHERE {where}"
        )

    if intent.target == "meeting_count":
        value_expr = "COUNT(DISTINCT t.id)"
    elif intent.target == "duration_seconds" and intent.operator in {"max", "min"}:
        direction = "DESC" if intent.operator == "max" else "ASC"
        return (
            "SELECT t.id::text AS transcript_id, t.session_id AS session_id, "
            "t.meeting_date::text AS meeting_date, t.participants AS participants, "
            "t.duration_seconds AS value, t.summary AS summary "
            "FROM transcripts t WHERE "
            f"{where} AND t.duration_seconds IS NOT NULL "
            f"ORDER BY t.duration_seconds {direction}, t.meeting_date {direction} LIMIT 1"
        )
    else:
        agg = "AVG" if intent.operator == "avg" else "SUM"
        value_expr = f"COALESCE({agg}(t.duration_seconds), 0)"

    if intent.group_by == "user_id":
        return (
            "SELECT t.user_id::text AS group_key, "
            f"{value_expr} AS value "
            "FROM transcripts t WHERE "
            f"{where} GROUP BY t.user_id ORDER BY value DESC LIMIT 20"
        )
    if intent.group_by == "day":
        return (
            "SELECT t.meeting_date::text AS group_key, "
            f"{value_expr} AS value "
            "FROM transcripts t WHERE "
            f"{where} GROUP BY t.meeting_date ORDER BY group_key LIMIT 31"
        )
    if intent.group_by == "speaker":
        return (
            "SELECT x.speaker AS group_key, "
            f"{value_expr} AS value "
            "FROM transcripts t "
            "JOIN (SELECT DISTINCT transcript_id, speaker FROM chunks_turn) x ON x.transcript_id = t.id "
            "WHERE "
            f"{where} GROUP BY x.speaker ORDER BY value DESC LIMIT 20"
        )
    return f"SELECT {value_expr} AS value FROM transcripts t WHERE {where}"


async def _run_numeric_query(
    conn: Any,
    intent: NumericIntent,
    params: list[Any],
    *,
    user_id: str,
    statement_timeout_ms: int,
) -> tuple[list[NumericRow], str]:
    where = _numeric_where_clause()

    if intent.target in {"speaking_time", "turn_count", "mention_count"}:
        sql = build_numeric_sql(intent)
        assert sql is not None
        rows = await _fetch_rows(conn, sql, params, user_id, statement_timeout_ms)
        if rows:
            return [NumericRow(value=float(rows[0]["value"] or 0))], sql
        return [NumericRow(value=0.0)], sql

    if intent.target == "meeting_count":
        value_expr = "COUNT(DISTINCT t.id)"
    elif intent.target == "duration_seconds" and intent.operator in {"max", "min"}:
        return await _run_duration_extreme(
            conn,
            intent,
            params,
            where,
            user_id=user_id,
            statement_timeout_ms=statement_timeout_ms,
        )
    else:
        agg = "AVG" if intent.operator == "avg" else "SUM"
        value_expr = f"COALESCE({agg}(t.duration_seconds), 0)"

    if intent.group_by == "user_id":
        sql = (
            "SELECT t.user_id::text AS group_key, "
            f"{value_expr} AS value "
            "FROM transcripts t WHERE "
            f"{where} GROUP BY t.user_id ORDER BY value DESC LIMIT 20"
        )
        rows = await _fetch_rows(conn, sql, params, user_id, statement_timeout_ms)
        return [NumericRow(group_key=r["group_key"], value=float(r["value"])) for r in rows], sql

    if intent.group_by == "day":
        sql = (
            "SELECT t.meeting_date::text AS group_key, "
            f"{value_expr} AS value "
            "FROM transcripts t WHERE "
            f"{where} GROUP BY t.meeting_date ORDER BY group_key LIMIT 31"
        )
        rows = await _fetch_rows(conn, sql, params, user_id, statement_timeout_ms)
        return [NumericRow(group_key=r["group_key"], value=float(r["value"])) for r in rows], sql

    if intent.group_by == "speaker":
        sql = (
            "SELECT x.speaker AS group_key, "
            f"{value_expr} AS value "
            "FROM transcripts t "
            "JOIN (SELECT DISTINCT transcript_id, speaker FROM chunks_turn) x ON x.transcript_id = t.id "
            "WHERE "
            f"{where} GROUP BY x.speaker ORDER BY value DESC LIMIT 20"
        )
        rows = await _fetch_rows(conn, sql, params, user_id, statement_timeout_ms)
        return [NumericRow(group_key=r["group_key"], value=float(r["value"])) for r in rows], sql

    sql = f"SELECT {value_expr} AS value FROM transcripts t WHERE {where}"
    rows = await _fetch_rows(conn, sql, params, user_id, statement_timeout_ms)
    if rows:
        return [NumericRow(value=float(rows[0]["value"] or 0))], sql
    return [NumericRow(value=0.0)], sql


async def _run_duration_extreme(
    conn: Any,
    intent: NumericIntent,
    params: list[Any],
    where: str,
    *,
    user_id: str,
    statement_timeout_ms: int,
) -> tuple[list[NumericRow], str]:
    sql = build_numeric_sql(intent)
    assert sql is not None
    rows = await _fetch_rows(conn, sql, params, user_id, statement_timeout_ms)
    if not rows:
        return [NumericRow(value=0.0, metadata={"no_data": True})], sql

    row = rows[0]
    metadata = {
        "transcript_id": row["transcript_id"],
        "session_id": row["session_id"],
        "meeting_date": row["meeting_date"],
        "participants": row["participants"],
        "summary": row["summary"],
    }
    return [NumericRow(value=float(row["value"] or 0), metadata=metadata)], sql


async def _fetch_rows(
    conn: Any,
    sql: str,
    params: list[Any],
    user_id: str,
    statement_timeout_ms: int,
) -> list[dict[str, Any]]:
    async with conn.transaction():
        await conn.execute("SET TRANSACTION READ ONLY")
        await conn.execute(f"SET LOCAL statement_timeout = {int(statement_timeout_ms)}")
        await conn.execute("SELECT set_config('app.current_user_id', $1, true)", str(user_id))
        rows = await conn.fetch(sql, *params)
    return [dict(r) for r in rows]
