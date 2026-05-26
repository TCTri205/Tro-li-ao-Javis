from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from javis_text2sql.llm.client import LLMClient

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


async def map_entities(question: str, db_conn: Any) -> dict[str, str]:
    rows = await db_conn.fetch(
        """
        SELECT alias, canonical_name
        FROM entity_aliases
        WHERE $1 ILIKE '%' || alias || '%'
           OR alias ILIKE '%' || $1 || '%'
        ORDER BY length(alias) DESC
        LIMIT 20
        """,
        question,
    )
    return {row["alias"]: row["canonical_name"] for row in rows}


async def generate_sql(
    question: str,
    entities: dict[str, str],
    llm_client: LLMClient,
    reference_date: date,
) -> str:
    system_prompt = build_sql_system_prompt(reference_date=reference_date, entity_map=entities)
    return clean_sql_markdown(await llm_client.generate(system=system_prompt, user=question))


async def refine_sql(
    question: str,
    failed_sql: str,
    error_message: str,
    llm_client: LLMClient,
    reference_date: date,
) -> str:
    prompt = build_refine_prompt(reference_date)
    user = f"Question: {question}\nFailed SQL: {failed_sql}\nDatabase error: {error_message}\nFix the SQL."
    return clean_sql_markdown(await llm_client.generate(system=prompt, user=user))


async def execute_readonly(conn: Any, sql: str, statement_timeout_ms: int = 5000) -> list[dict[str, Any]]:
    async with conn.transaction():
        await conn.execute("SET TRANSACTION READ ONLY")
        await conn.execute(f"SET LOCAL statement_timeout = {int(statement_timeout_ms)}")
        rows = await conn.fetch(sql)
    return [dict(row) for row in rows]


async def text2sql_pipeline(
    question: str,
    db_pool: Any,
    llm_client: LLMClient,
    reference_date: date,
    statement_timeout_ms: int = 5000,
) -> Text2SQLResult:
    async with db_pool.acquire() as conn:
        entities = await map_entities(question, conn)
        sql = await generate_sql(question, entities, llm_client, reference_date)
        validation = validate_sql(sql)
        if not validation.ok:
            return Text2SQLResult(
                success=False,
                sql=sql,
                error=f"Security validation failed: {validation.error}",
            )

        try:
            data = await execute_readonly(conn, sql, statement_timeout_ms=statement_timeout_ms)
            return Text2SQLResult(success=True, sql=sql, data=data)
        except Exception as db_error:
            logger.warning("SQL execution failed, retrying once: %s", db_error)
            refined_sql = await refine_sql(question, sql, str(db_error), llm_client, reference_date)
            refined_validation = validate_sql(refined_sql)
            if not refined_validation.ok:
                return Text2SQLResult(
                    success=False,
                    sql=refined_sql,
                    error=f"Refined SQL validation failed: {refined_validation.error}",
                    retry_used=True,
                )

            try:
                data = await execute_readonly(conn, refined_sql, statement_timeout_ms=statement_timeout_ms)
                return Text2SQLResult(success=True, sql=refined_sql, data=data, retry_used=True)
            except Exception as retry_error:
                return Text2SQLResult(
                    success=False,
                    sql=refined_sql,
                    error=f"Execution failed after retry: {retry_error}",
                    retry_used=True,
                )
