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
    
    # Strip block comments /* ... */
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    
    # Strip single-line comments -- ...
    cleaned_lines = []
    for line in sql.splitlines():
        cleaned_lines.append(re.sub(r"--.*$", "", line))
    sql = "\n".join(cleaned_lines).strip()
    
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


def validate_sql(sql: str, question: str | None = None, allow_fallback: bool = True) -> SqlValidationResult:
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

        # --- ADVANCED AST SEMANTIC CHECKS ---
        
        # 1. Block Star (*) and COUNT(*)
        if parsed.find(exp.Star) is not None:
            return SqlValidationResult(
                False, 
                "Anti-pattern detected: Do not use SELECT * or COUNT(*). Please select explicit columns or use COUNT(1)."
            )

        # 2. Block completed status on v_commitments
        if "v_commitments" in tables:
            for eq in parsed.find_all(exp.EQ):
                left, right = eq.left, eq.right
                if isinstance(left, exp.Column) and left.name.lower() == "status":
                    if isinstance(right, exp.Literal) and right.this.lower() in ("completed", "success"):
                        return SqlValidationResult(
                            False,
                            "Database schema mismatch: 'completed' status is invalid. Use status = 'done' for completed commitments."
                        )

        # 3. Require source_type filter when querying v_topics
        if "v_topics" in tables:
            columns = [c.name.lower() for c in parsed.find_all(exp.Column)]
            if "source_type" not in columns:
                return SqlValidationResult(
                    False,
                    "Semantic rule violated: Querying 'v_topics' requires explicit filtering on 'source_type' (e.g. source_type = 'topic' or source_type = 'entity')."
                )

        # 4. Enforce DISTINCT when query asks for different/unique items
        if question and ("異なる" in question or "different" in question.lower()):
            has_distinct = parsed.args.get("distinct") is not None
            if not has_distinct:
                # Check inside COUNT function as well
                count_distinct = False
                for count_func in parsed.find_all(exp.Count):
                    if count_func.args.get("distinct"):
                        count_distinct = True
                if not count_distinct:
                    return SqlValidationResult(
                        False,
                        "Semantic rule violated: Query asks for different/distinct items but SQL is missing the DISTINCT keyword."
                    )

        return SqlValidationResult(True)
    except Exception as exc:
        return SqlValidationResult(False, f"SQL parse error: {exc}")
