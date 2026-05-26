from __future__ import annotations

import re
from dataclasses import dataclass

from .prompt import ALLOWED_VIEWS


FORBIDDEN_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "CALL",
    "COPY",
    "GRANT",
    "REVOKE",
    "SET",
}


@dataclass(frozen=True)
class SqlValidationResult:
    ok: bool
    error: str = ""
    parser: str = "sqlglot"


def clean_sql_markdown(raw_sql: str) -> str:
    sql = raw_sql.strip()
    fence_match = re.search(r"```(?:sql)?\s*(.*?)```", sql, flags=re.IGNORECASE | re.DOTALL)
    if fence_match:
        sql = fence_match.group(1).strip()
    return sql.strip()


def _contains_forbidden_keyword(sql: str) -> str | None:
    upper = sql.upper()
    for keyword in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", upper):
            return keyword
    return None


def _fallback_validate(sql: str) -> SqlValidationResult:
    normalized = sql.strip().rstrip(";").strip()
    if ";" in normalized:
        return SqlValidationResult(False, "multiple SQL statements are not allowed", parser="fallback")
    if not re.match(r"^(WITH\s+.+\s+SELECT|SELECT)\b", normalized, flags=re.IGNORECASE | re.DOTALL):
        return SqlValidationResult(False, "only SELECT statements are allowed", parser="fallback")
    forbidden = _contains_forbidden_keyword(normalized)
    if forbidden:
        return SqlValidationResult(False, f"forbidden keyword: {forbidden}", parser="fallback")

    table_names = re.findall(r"\b(?:FROM|JOIN)\s+([a-zA-Z_][\w.]*)", normalized, flags=re.IGNORECASE)
    bad = sorted({name.split(".")[-1] for name in table_names if name.split(".")[-1] not in ALLOWED_VIEWS})
    if bad:
        return SqlValidationResult(False, f"only allowed semantic views can be queried: {bad}", parser="fallback")
    return SqlValidationResult(True, parser="fallback")


def validate_sql(sql: str, allow_fallback: bool = True) -> SqlValidationResult:
    sql = clean_sql_markdown(sql)
    if not sql:
        return SqlValidationResult(False, "empty SQL")
    if sql.count(";") > 1 or (";" in sql.rstrip(";")):
        return SqlValidationResult(False, "multiple SQL statements are not allowed")
    forbidden = _contains_forbidden_keyword(sql)
    if forbidden:
        return SqlValidationResult(False, f"forbidden keyword: {forbidden}")

    try:
        import sqlglot
        from sqlglot import expressions as exp
    except ModuleNotFoundError:
        if allow_fallback:
            return _fallback_validate(sql)
        return SqlValidationResult(False, "sqlglot is not installed")

    try:
        parsed_items = sqlglot.parse(sql, read="postgres")
        parsed_items = [item for item in parsed_items if item is not None]
        if len(parsed_items) != 1:
            return SqlValidationResult(False, "exactly one SQL statement is required")
        parsed = parsed_items[0]
        if not isinstance(parsed, (exp.Select, exp.Union, exp.With)):
            return SqlValidationResult(False, "only SELECT statements are allowed")

        bad_expressions = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Command)
        if any(parsed.find(expr_type) is not None for expr_type in bad_expressions):
            return SqlValidationResult(False, "write or DDL statements are not allowed")

        tables = [table.name for table in parsed.find_all(exp.Table)]
        bad_tables = sorted({table for table in tables if table not in ALLOWED_VIEWS})
        if bad_tables:
            return SqlValidationResult(False, f"only allowed semantic views can be queried: {bad_tables}")
        return SqlValidationResult(True)
    except Exception as exc:
        return SqlValidationResult(False, f"SQL parse error: {exc}")
