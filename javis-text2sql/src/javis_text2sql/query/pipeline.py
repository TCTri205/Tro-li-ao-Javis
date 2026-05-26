from __future__ import annotations

import logging
import re
import unicodedata
import json
import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from rapidfuzz import fuzz
import redis

from javis_text2sql.config import Settings
from javis_text2sql.llm.client import LLMClient
from javis_text2sql.llm.embeddings import EmbeddingClient, get_embedding_client

from .prompt import build_refine_prompt, build_sql_system_prompt
from .sql_validation import clean_sql_markdown, validate_sql


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Text2SQLResult:
    success: bool
    sql: str
    data: list[dict[str, Any]] | None = None
    error: str | None = None
    retry_used: bool = False


class RedisCache:
    def __init__(self, redis_url: str | None = None) -> None:
        self.redis_url = redis_url
        self._client = None
        self._is_available = False
        if redis_url:
            try:
                self._client = redis.from_url(redis_url, socket_timeout=1.0, socket_connect_timeout=1.0)
                self._client.ping()
                self._is_available = True
                logger.info("Successfully connected to Redis at %s", redis_url)
            except Exception as e:
                logger.warning("Redis is not available, running without cache: %s", e)
                self._client = None
                self._is_available = False

    def _normalize_key(self, question: str, user_id: str, reference_date: date) -> str:
        norm_q = normalize_japanese(question)
        return f"text2sql:{norm_q}:{user_id}:{reference_date.isoformat()}"

    def get(self, question: str, user_id: str, reference_date: date) -> Text2SQLResult | None:
        if not self._is_available or not self._client:
            return None
        key = self._normalize_key(question, user_id, reference_date)
        try:
            val = self._client.get(key)
            if val:
                data = json.loads(val.decode("utf-8"))
                logger.info("Cache HIT for key: %s", key)
                return Text2SQLResult(
                    success=data["success"],
                    sql=data["sql"],
                    data=data.get("data"),
                    error=data.get("error"),
                    retry_used=data.get("retry_used", False),
                )
        except Exception as e:
            logger.warning("Redis GET failed: %s", e)
        return None

    def set(self, question: str, user_id: str, reference_date: date, result: Text2SQLResult, ttl: int = 3600) -> None:
        if not self._is_available or not self._client:
            return
        key = self._normalize_key(question, user_id, reference_date)
        try:
            payload = {
                "success": result.success,
                "sql": result.sql,
                "data": result.data,
                "error": result.error,
                "retry_used": result.retry_used,
            }
            self._client.setex(key, ttl, json.dumps(payload, ensure_ascii=False))
            logger.info("Cache SET for key: %s", key)
        except Exception as e:
            logger.warning("Redis SET failed: %s", e)


def normalize_japanese(text: str) -> str:
    # NFKC normalizes full-width Roman letters/numbers to half-width,
    # and half-width katakana to full-width.
    text = unicodedata.normalize("NFKC", text)
    text = text.lower()
    # Remove standard spaces and Japanese/English punctuation
    text = re.sub(r"[\s　.,、。/・_ー\-_]+", "", text)
    return text


def generate_temporal_context(reference_date: date) -> str:
    ref = reference_date
    weekday = ref.weekday()  # 0 = Monday, 6 = Sunday

    # This week (Monday to Sunday)
    this_week_start = ref - timedelta(days=weekday)
    this_week_end = this_week_start + timedelta(days=6)

    # Next week
    next_week_start = this_week_start + timedelta(days=7)
    next_week_end = next_week_start + timedelta(days=6)

    # Last week
    last_week_start = this_week_start - timedelta(days=7)
    last_week_end = last_week_start + timedelta(days=6)

    # This month
    this_month_start = date(ref.year, ref.month, 1)
    _, last_day = calendar.monthrange(ref.year, ref.month)
    this_month_end = date(ref.year, ref.month, last_day)

    # Next month
    if ref.month == 12:
        next_month_start = date(ref.year + 1, 1, 1)
    else:
        next_month_start = date(ref.year, ref.month + 1, 1)
    _, next_last_day = calendar.monthrange(next_month_start.year, next_month_start.month)
    next_month_end = date(next_month_start.year, next_month_start.month, next_last_day)

    # Last month
    if ref.month == 1:
        last_month_start = date(ref.year - 1, 12, 1)
    else:
        last_month_start = date(ref.year, ref.month - 1, 1)
    _, last_last_day = calendar.monthrange(last_month_start.year, last_month_start.month)
    last_month_end = date(last_month_start.year, last_month_start.month, last_last_day)

    # Yesterday and tomorrow
    yesterday = ref - timedelta(days=1)
    tomorrow = ref + timedelta(days=1)

    return f"""Temporal Context (Relative Date Resolution Helper):
- Current reference date (today/今日): {ref.isoformat()}
- Yesterday (昨日): {yesterday.isoformat()}
- Tomorrow (明日): {tomorrow.isoformat()}
- This week (今週): {this_week_start.isoformat()} to {this_week_end.isoformat()}
- Next week (来週): {next_week_start.isoformat()} to {next_week_end.isoformat()}
- Last week (先週): {last_week_start.isoformat()} to {last_week_end.isoformat()}
- This month (今月): {this_month_start.isoformat()} to {this_month_end.isoformat()}
- Next month (来月): {next_month_start.isoformat()} to {next_month_end.isoformat()}
- Last month (先学): {last_month_start.isoformat()} to {last_month_end.isoformat()}
Use these exact date ranges in your SQL generation when the user uses these relative terms.
"""


async def retrieve_few_shots(
    question: str,
    db_conn: Any,
    embedding_client: EmbeddingClient | None = None,
    limit: int = 3,
) -> list[tuple[str, str]]:
    from .prompt import FEW_SHOT_EXAMPLES

    try:
        table_exists = await db_conn.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'golden_queries'
            )
            """
        )
        if not table_exists:
            return FEW_SHOT_EXAMPLES[:limit]

        embed_client = embedding_client or get_embedding_client()
        embeddings = await embed_client.embed_texts([question])
        if not embeddings:
            return FEW_SHOT_EXAMPLES[:limit]

        emb = embeddings[0]
        rows = await db_conn.fetch(
            """
            SELECT question, sql
            FROM golden_queries
            ORDER BY embedding <=> $1::vector
            LIMIT $2
            """,
            str(emb),
            limit,
        )
        if not rows:
            return FEW_SHOT_EXAMPLES[:limit]
        return [(r["question"], r["sql"]) for r in rows]
    except Exception as e:
        logger.warning("Dynamic few-shot retrieval failed, falling back to static examples: %s", e)
        return FEW_SHOT_EXAMPLES[:limit]


async def map_entities(question: str, db_conn: Any) -> dict[str, str]:
    try:
        rows = await db_conn.fetch(
            """
            SELECT alias, canonical_name, similarity(alias, $1) as sim
            FROM entity_aliases
            WHERE similarity(alias, $1) > 0.05 OR $1 ILIKE '%' || alias || '%'
            ORDER BY sim DESC
            LIMIT 200
            """,
            question,
        )
    except Exception as e:
        logger.warning("pg_trgm candidate selection failed, falling back to full scan: %s", e)
        rows = await db_conn.fetch(
            """
            SELECT alias, canonical_name
            FROM entity_aliases
            """
        )

    if not rows:
        return {}

    norm_question = normalize_japanese(question)
    if not norm_question:
        return {}

    matched = {}
    for row in rows:
        alias = row["alias"]
        canonical = row["canonical_name"]
        norm_alias = normalize_japanese(alias)
        if not norm_alias:
            continue

        # Exact normalized substring match gets highest priority
        if norm_alias in norm_question:
            matched[alias] = (canonical, 100, len(alias))
            continue

        # Fuzzy partial match using rapidfuzz
        score = fuzz.partial_ratio(norm_alias, norm_question)
        if score >= 85:
            matched[alias] = (canonical, score, len(alias))

    # Sort matches by score descending, then alias length descending
    sorted_matches = sorted(matched.items(), key=lambda x: (x[1][1], x[1][2]), reverse=True)

    result = {}
    seen_canonicals = set()
    for alias, (canonical, score, _) in sorted_matches:
        if canonical not in seen_canonicals:
            result[alias] = canonical
            seen_canonicals.add(canonical)
            if len(result) >= 10:
                break

    return result


async def generate_sql(
    question: str,
    entities: dict[str, str],
    llm_client: LLMClient,
    reference_date: date,
    few_shots: list[tuple[str, str]],
) -> str:
    system_prompt = build_sql_system_prompt(reference_date=reference_date, entity_map=entities)
    
    # Inject dynamic few-shots and relative temporal context
    rendered_few_shots = "\n\n".join(f"Question: {q}\nSQL: {s}" for q, s in few_shots)
    temporal_block = generate_temporal_context(reference_date)

    enriched_system_prompt = f"""{system_prompt}
{temporal_block}

Few-shot examples:
{rendered_few_shots}
"""
    return clean_sql_markdown(await llm_client.generate(system=enriched_system_prompt, user=question))


async def refine_sql(
    question: str,
    failed_sql: str,
    error_message: str,
    llm_client: LLMClient,
    reference_date: date,
) -> str:
    prompt = build_refine_prompt(reference_date)
    temporal_block = generate_temporal_context(reference_date)
    
    enriched_prompt = f"""{prompt}
{temporal_block}
"""
    user = f"Question: {question}\nFailed SQL: {failed_sql}\nDatabase error: {error_message}\nFix the SQL."
    return clean_sql_markdown(await llm_client.generate(system=enriched_prompt, user=user))


async def execute_readonly(
    conn: Any,
    sql: str,
    user_id: str = "00000000-0000-0000-0000-000000000000",
    statement_timeout_ms: int = 5000,
) -> list[dict[str, Any]]:
    async with conn.transaction():
        await conn.execute("SET TRANSACTION READ ONLY")
        await conn.execute(f"SET LOCAL statement_timeout = {int(statement_timeout_ms)}")
        await conn.execute("SELECT set_config('app.current_user_id', $1, true)", str(user_id))
        rows = await conn.fetch(sql)
    return [dict(row) for row in rows]


async def text2sql_pipeline(
    question: str,
    db_pool: Any,
    llm_client: LLMClient,
    reference_date: date,
    user_id: str = "00000000-0000-0000-0000-000000000000",
    statement_timeout_ms: int = 5000,
    redis_url: str | None = None,
) -> Text2SQLResult:
    # Resolve redis_url from settings if not explicitly provided
    r_url = redis_url or Settings.from_env().redis_url
    cache = RedisCache(r_url)
    
    # 1. Cache Lookup
    cached_result = cache.get(question, user_id, reference_date)
    if cached_result:
        return cached_result

    async with db_pool.acquire() as conn:
        # 2. Entity Mapping with pg_trgm
        entities = await map_entities(question, conn)
        
        # 3. Dynamic Few-Shot Retrieval via pgvector
        few_shots = await retrieve_few_shots(question, conn)

        # 4. SQL Generation
        sql = await generate_sql(question, entities, llm_client, reference_date, few_shots)
        
        # 5. Security Validation
        validation = validate_sql(sql)
        if not validation.ok:
            result = Text2SQLResult(
                success=False,
                sql=sql,
                error=f"Security validation failed: {validation.error}",
            )
            cache.set(question, user_id, reference_date, result)
            return result

        # 6. Database Execution with 1-turn retry
        try:
            data = await execute_readonly(conn, sql, user_id=user_id, statement_timeout_ms=statement_timeout_ms)
            result = Text2SQLResult(success=True, sql=sql, data=data)
            cache.set(question, user_id, reference_date, result)
            return result
        except Exception as db_error:
            logger.warning("SQL execution failed, retrying once: %s", db_error)
            refined_sql = await refine_sql(question, sql, str(db_error), llm_client, reference_date)
            refined_validation = validate_sql(refined_sql)
            if not refined_validation.ok:
                result = Text2SQLResult(
                    success=False,
                    sql=refined_sql,
                    error=f"Refined SQL validation failed: {refined_validation.error}",
                    retry_used=True,
                )
                cache.set(question, user_id, reference_date, result)
                return result

            try:
                data = await execute_readonly(conn, refined_sql, user_id=user_id, statement_timeout_ms=statement_timeout_ms)
                result = Text2SQLResult(success=True, sql=refined_sql, data=data, retry_used=True)
                cache.set(question, user_id, reference_date, result)
                return result
            except Exception as retry_error:
                result = Text2SQLResult(
                    success=False,
                    sql=refined_sql,
                    error=f"Execution failed after retry: {retry_error}",
                    retry_used=True,
                )
                cache.set(question, user_id, reference_date, result)
                return result

