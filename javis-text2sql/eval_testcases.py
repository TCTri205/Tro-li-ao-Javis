"""
Javis Text2SQL — 100 Test Case Evaluator with Semantic Diagnostics
=================================================================
Đánh giá toàn diện 102 test case từ testcase-text2sql.csv theo 5 chiều:
  1. SQL Syntax Validity    — Parse bằng sqlglot AST
  2. Security Compliance    — Chỉ cho phép SELECT trên 8 allowed views
  3. Schema Correctness     — Columns & views có tồn tại trong schema không
  4. Live Execution         — Chạy thực trên PostgreSQL và trả kết quả
  5. Semantic Quality       — Đánh giá ngữ nghĩa 7 chiều (Zero-shot NLP + AST)
"""
from __future__ import annotations

import asyncio
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import sqlglot
import sqlglot.errors

# ── Allowed views & their known columns (from migrations/001_init.sql) ─────────
ALLOWED_VIEWS = {
    "v_topics": {
        "meeting_id", "meeting_title", "meeting_date", "passage_id", "topic", "source_type"
    },
    "v_commitments": {
        "meeting_id", "meeting_title", "meeting_date", "passage_id", "commitment_id",
        "person", "action", "deadline", "deadline_date", "status"
    },
    "v_amounts": {
        "meeting_id", "meeting_title", "meeting_date", "passage_id",
        "amount_value", "amount_unit", "amount_currency", "amount_context"
    },
    "v_action_items": {
        "meeting_id", "meeting_title", "meeting_date", "passage_id",
        "action_item_text", "importance_score"
    },
    "v_open_questions": {
        "meeting_id", "meeting_title", "meeting_date", "passage_id",
        "question_text", "importance_score"
    },
    "v_statements": {
        "meeting_id", "meeting_title", "meeting_date", "passage_id",
        "turn_types", "has_action_item", "has_question", "sentiment",
        "importance_score", "content"
    },
    "v_dates": {
        "meeting_id", "meeting_title", "meeting_date", "passage_id",
        "date_raw_text", "date_resolved", "confidence"
    },
    "v_speaker_turns": {
        "meeting_id", "meeting_title", "meeting_date", "speaker",
        "turn_content", "timestamp", "turn_types", "sentiment", "importance_score"
    },
}

FORBIDDEN_KEYWORDS = {"drop", "delete", "insert", "update", "truncate", "alter", "create", "grant", "revoke"}

VIEW_KEYWORDS = {
    "v_commitments": ["コミットメント", "期限", "担当", "deadline", "status"],
    "v_action_items": ["アクションアイテム", "action_item", "タスク"],
    "v_open_questions": ["質問", "未解決", "question", "未回答", "オープンな質問"],
    "v_amounts": ["金額", "予算", "budget", "amount", "jpy", "通貨", "総額", "総予算", "値"],
    "v_topics": ["トピック", "エンティティ", "entity", "source_type", "会社紹介", "会社概要"],
    "v_speaker_turns": ["発話", "話者", "speaker", "発言数", "ターン", "発言者"],
    "v_dates": ["日付", "確信", "confidence", "date_resolved", "date_raw"],
    "v_statements": ["発言", "感情", "sentiment", "重要度", "importance", "ネガティブ", "コンテンツ", "ステートメント"]
}

# ── ANSI colors ────────────────────────────────────────────────────────────────
G  = "\033[92m";  Y  = "\033[93m";  R  = "\033[91m"
CY = "\033[96m";  MG = "\033[95m";  B  = "\033[1m";  RS = "\033[0m"


# ══════════════════════════════════════════════════════════════════════════════
# Static Analysis (no DB required)
# ══════════════════════════════════════════════════════════════════════════════

def check_syntax(sql: str) -> tuple[bool, str]:
    """Parse SQL với sqlglot — trả (ok, error_msg)."""
    try:
        stmts = sqlglot.parse(sql, dialect="postgres", error_level=sqlglot.ErrorLevel.RAISE)
        if not stmts or stmts[0] is None:
            return False, "Empty parse result"
        return True, ""
    except sqlglot.errors.ParseError as e:
        return False, str(e)


def check_security(sql: str) -> tuple[bool, str]:
    """Kiểm tra forbidden keywords và chỉ cho phép SELECT."""
    lower = sql.lower()
    for kw in FORBIDDEN_KEYWORDS:
        if kw in lower.split() or f" {kw} " in lower or lower.startswith(kw):
            return False, f"Forbidden keyword: {kw.upper()}"
    try:
        stmts = sqlglot.parse(sql, dialect="postgres")
        for stmt in stmts:
            if stmt and not isinstance(stmt, sqlglot.expressions.Select):
                return False, f"Non-SELECT statement: {type(stmt).__name__}"
    except Exception:
        pass  # parse errors handled separately
    return True, ""


def extract_table_refs(sql: str) -> list[str]:
    """Trích xuất tên bảng/view được tham chiếu trong SQL."""
    try:
        stmts = sqlglot.parse(sql, dialect="postgres")
        tables = []
        for stmt in stmts:
            if stmt:
                for table in stmt.find_all(sqlglot.expressions.Table):
                    tables.append(table.name.lower())
        return list(set(tables))
    except Exception:
        return []


def check_schema(sql: str) -> tuple[bool, str, list[str]]:
    """
    Kiểm tra:
      - Tất cả bảng/view được dùng có nằm trong ALLOWED_VIEWS không
      - Cột được SELECT có tồn tại trong view tương ứng không (best-effort)
    Trả (ok, error_msg, unknown_tables)
    """
    table_refs = extract_table_refs(sql)
    unknown = [t for t in table_refs if t not in ALLOWED_VIEWS]
    if unknown:
        return False, f"Unknown table(s)/view(s): {unknown}", unknown
    return True, "", []


def static_eval(sql: str) -> dict[str, Any]:
    """Chạy toàn bộ kiểm tra tĩnh, trả dict kết quả."""
    syn_ok, syn_err   = check_syntax(sql)
    sec_ok, sec_err   = check_security(sql)
    sch_ok, sch_err, unknown_tables = check_schema(sql)

    tables = extract_table_refs(sql)
    all_ok = syn_ok and sec_ok and sch_ok

    return {
        "syntax_ok":    syn_ok,
        "syntax_error": syn_err,
        "security_ok":  sec_ok,
        "security_error": sec_err,
        "schema_ok":    sch_ok,
        "schema_error": sch_err,
        "unknown_tables": unknown_tables,
        "referenced_views": tables,
        "static_pass":  all_ok,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Semantic Quality Diagnostic Layer
# ══════════════════════════════════════════════════════════════════════════════

def check_hallucinated_columns(parsed_expr) -> list[str]:
    """Phát hiện các cột ảo không tồn tại trong schema của view."""
    table_map = {}
    for table in parsed_expr.find_all(sqlglot.expressions.Table):
        table_name = table.name.lower()
        alias = table.alias.lower() if table.alias else table_name
        table_map[alias] = table_name
        table_map[table_name] = table_name

    errors = []
    select_aliases = set()
    for select in parsed_expr.find_all(sqlglot.expressions.Select):
        for projection in select.expressions:
            if isinstance(projection, sqlglot.expressions.Alias):
                select_aliases.add(projection.alias.lower())

    for col in parsed_expr.find_all(sqlglot.expressions.Column):
        col_name = col.name.lower()
        col_table = col.table.lower() if col.table else ""
        
        if col_name in select_aliases and not col_table:
            continue
            
        if col_table:
            actual_table = table_map.get(col_table)
            if actual_table and actual_table in ALLOWED_VIEWS:
                if col_name not in ALLOWED_VIEWS[actual_table]:
                    errors.append(f"Hallucinated column: '{col_name}' in view '{actual_table}'")
        else:
            found = False
            referenced_views = list(set(table_map.values()))
            if not referenced_views:
                continue
            for view in referenced_views:
                if view in ALLOWED_VIEWS and col_name in ALLOWED_VIEWS[view]:
                    found = True
                    break
            
            if not found:
                common_aliases = {
                    "total_amount", "commitment_count", "completed_commitments", "topic_count", 
                    "statement_count", "amount_count", "entity", "completed_tasks", 
                    "action_item_count", "avg_importance", "question_count"
                }
                if col_name not in common_aliases:
                    if len(referenced_views) == 1:
                        view = referenced_views[0]
                        if view in ALLOWED_VIEWS and col_name not in ALLOWED_VIEWS[view]:
                            errors.append(f"Hallucinated column: '{col_name}' in view '{view}'")
                    elif len(referenced_views) > 1:
                        errors.append(f"Column '{col_name}' not found in any of referenced views {referenced_views}")
    return errors


def semantic_eval(query: str, sql: str, static_res: dict) -> dict[str, Any]:
    """Đánh giá chất lượng ngữ nghĩa của SQL trên 7 chiều năng lực."""
    # 1. Trích xuất mong đợi từ NL query
    expected_views = []
    
    # Overrides for explicit view calls
    if "topicsから" in query or "topicsの" in query or "トピックの" in query:
        expected_views = ["v_topics"]
    elif "commitmentsから" in query or "commitmentsの" in query or "コミットメントの" in query:
        expected_views = ["v_commitments"]
    else:
        for view, keywords in VIEW_KEYWORDS.items():
            if any(kw.lower() in query.lower() for kw in keywords):
                expected_views.append(view)
                
        if "発言" in query and "感情" not in query and "発言数" not in query:
            if "v_statements" not in expected_views:
                expected_views.append("v_statements")
            if "v_speaker_turns" not in expected_views:
                expected_views.append("v_speaker_turns")

    expected_filters = []
    if "未完了" in query:
        expected_filters.append(("status", "pending"))
    elif "完了" in query or "解決済" in query:
        expected_filters.append(("status", "done")) 
        
    if "ネガティブ" in query:
        expected_filters.append(("sentiment", "negative"))
    if "エンティティ" in query:
        expected_filters.append(("source_type", "entity"))
        
    for kw in ["VJ Technologies", "AJ Technologies", "Energy Japan", "ONE Financial", "Housing", "electric", "Yamashita", "Yoshio"]:
        if kw.lower() in query.lower():
            expected_filters.append(("any", kw))

    expected_aggs = []
    if any(x in query for x in ["合計", "総", "SUM"]):
        expected_aggs.append("sum")
    if any(x in query for x in ["数", "件数", "いくつ", "カウント"]):
        expected_aggs.append("count")
    if "平均" in query:
        expected_aggs.append("avg")

    is_distinct = any(x in query for x in ["異なる", "重複を除く", "DISTINCT", "ユニーク"])
    
    expected_order = None
    if any(x in query for x in ["降順", "多い", "高い"]):
        expected_order = "desc"
    elif any(x in query for x in ["昇順", "低い", "古い"]):
        expected_order = "asc"
        
    is_limit = any(x in query for x in ["上位", "LIMIT", "最初の"])

    # 2. Phân tích AST SQL
    actual_views = static_res.get("referenced_views", [])
    
    dim_scores = {
        "view_selection": 1.0,
        "filter_check": 1.0,
        "column_check": 1.0,
        "aggregation": 1.0,
        "structure": 1.0,
        "cross_view": 1.0,
        "anti_patterns": 1.0
    }
    dim_details = {k: [] for k in dim_scores}

    try:
        parsed = sqlglot.parse_one(sql, dialect="postgres")
    except Exception as e:
        return {
            "semantic_score": 0.0,
            "severity": "error",
            "diagnostics": {"parsing_failed": [str(e)]},
            "scores": dim_scores,
            "details": dim_details
        }

    # ── Dim A: View Selection ──
    if expected_views:
        intersection = set(expected_views) & set(actual_views)
        if not intersection:
            dim_scores["view_selection"] = 0.0
            dim_details["view_selection"].append(f"Incorrect view selection: used {actual_views}, expected {expected_views}")
        elif len(intersection) < len(actual_views):
            dim_scores["view_selection"] = 0.5
            dim_details["view_selection"].append(f"Partial view match: used {actual_views}, expected {expected_views}")

    # ── Dim B: Filter Completeness ──
    sql_lower = sql.lower()
    for filter_type, val in expected_filters:
        if filter_type == "status":
            if val == "pending":
                if "pending" not in sql_lower:
                    dim_scores["filter_check"] = 0.0
                    dim_details["filter_check"].append("Missing expected filter condition: status = 'pending'")
            elif val == "done":
                if "completed" in sql_lower:
                    dim_scores["filter_check"] = 0.0
                    dim_details["filter_check"].append("Sai (do sql dùng status = 'completed' nhưng trong DB lại định nghĩa status IN ('pending', 'done', 'cancelled')) -> ko có completed")
                elif "done" not in sql_lower:
                    dim_scores["filter_check"] = 0.0
                    dim_details["filter_check"].append("Missing expected filter condition: status = 'done'")
        elif filter_type == "sentiment":
            if "negative" not in sql_lower:
                dim_scores["filter_check"] = 0.0
                dim_details["filter_check"].append("Missing expected filter condition: sentiment = 'negative'")
        elif filter_type == "source_type":
            if "entity" not in sql_lower:
                dim_scores["filter_check"] = 0.0
                dim_details["filter_check"].append("Missing expected filter condition: source_type = 'entity'")
        elif filter_type == "any":
            if val.lower() not in sql_lower:
                dim_scores["filter_check"] = 0.5
                dim_details["filter_check"].append(f"Missing search term filter: '{val}'")

    # ── Strict Topic and Entity checks matching user criteria ──
    if "トピック" in query:
        is_source_type_breakdown = "source_type" in query and "ごと" in query
        asks_for_entity = "entity" in query or "エンティティ" in query
        if not is_source_type_breakdown and not asks_for_entity:
            has_topic_filter = any(x in sql_lower for x in ["'topic'", '"topic"', "'%topic%'", '"%topic%"'])
            if not has_topic_filter:
                dim_scores["filter_check"] = 0.0
                dim_details["filter_check"].append("Sai (trả dư entity, thừa rows / thiếu filter: source_type = 'topic')")
            
    if "固有エンティティ" in query or "エンティティ" in query:
        is_source_type_breakdown = "source_type" in query and "ごと" in query
        if not is_source_type_breakdown:
            has_entity_filter = any(x in sql_lower for x in ["'entity'", '"entity"', "'%entity%'", '"%entity%"'])
            if not has_entity_filter:
                dim_scores["filter_check"] = 0.0
                dim_details["filter_check"].append("Sai (KHÔNG trả entities / semantic sai hoàn toàn, query sai bảng)")
            if "v_topics" not in actual_views:
                dim_scores["view_selection"] = 0.0
                dim_details["view_selection"].append("Sai (KHÔNG trả entities / semantic sai hoàn toàn, query sai bảng)")
            if "topic" not in sql_lower:
                dim_scores["column_check"] = 0.0
                dim_details["column_check"].append("Sai (KHÔNG trả entities / semantic sai hoàn toàn, query sai bảng)")

    # ── Redundant GROUP BY check ──
    if "総予算" in query and "group by" in sql_lower:
        dim_scores["anti_patterns"] = 0.5
        dim_details["anti_patterns"].append("Đúng (GROUP BY amount_currency dư thừa)")

    # ── Dim C: Column Relevance ──
    if "*" in sql:
        dim_scores["column_check"] = 0.5
        dim_details["column_check"].append("SELECT * used instead of explicit column selection")
    else:
        for view in actual_views:
            if view == "v_topics":
                if "topic" not in sql_lower and "meeting_title" not in sql_lower:
                    dim_scores["column_check"] = 0.5
                    dim_details["column_check"].append("Missing key columns in SELECT: ['topic'] or ['meeting_title']")

    # ── Dim D: Aggregation Logic ──
    actual_aggs = []
    for agg in parsed.find_all(sqlglot.expressions.Anonymous):
        actual_aggs.append(agg.name.lower())
    for agg in parsed.find_all(sqlglot.expressions.Sum):
        actual_aggs.append("sum")
    for agg in parsed.find_all(sqlglot.expressions.Count):
        actual_aggs.append("count")
    for agg in parsed.find_all(sqlglot.expressions.Avg):
        actual_aggs.append("avg")

    has_group_by = parsed.args.get("group") is not None

    for agg in expected_aggs:
        if agg == "sum" and "sum" not in actual_aggs:
            dim_scores["aggregation"] = 0.0
            dim_details["aggregation"].append("Expected SUM aggregation, but it was not found")
        elif agg == "count" and "count" not in actual_aggs:
            dim_scores["aggregation"] = 0.0
            dim_details["aggregation"].append("Expected COUNT aggregation, but it was not found")
        elif agg == "avg" and "avg" not in actual_aggs:
            dim_scores["aggregation"] = 0.0
            dim_details["aggregation"].append("Expected AVG aggregation, but it was not found")

    if any(x in query for x in ["ごとに", "別"]) and not has_group_by:
        dim_scores["aggregation"] = 0.0
        dim_details["aggregation"].append("Expected GROUP BY clause for breakdown query, but it was missing")

    # ── Dim E: Structural Correctness ──
    actual_orders = []
    for order in parsed.find_all(sqlglot.expressions.Ordered):
        is_desc = order.args.get("desc")
        actual_orders.append("desc" if is_desc else "asc")

    if expected_order:
        if not actual_orders:
            dim_scores["structure"] = 0.5
            dim_details["structure"].append(f"Missing ORDER BY clause (expected {expected_order.upper()})")
        elif expected_order not in actual_orders:
            dim_scores["structure"] = 0.0
            dim_details["structure"].append(f"Incorrect sort direction: expected {expected_order.upper()}")

    is_sql_distinct = parsed.args.get("distinct") is not None
    if is_distinct and not is_sql_distinct:
        dim_scores["structure"] = 0.5
        dim_details["structure"].append("Missing DISTINCT clause (expected unique result)")

    is_sql_limit = parsed.args.get("limit") is not None
    if is_limit and not is_sql_limit:
        dim_scores["structure"] = 0.5
        dim_details["structure"].append("Missing LIMIT clause (expected top-N constraint)")

    # ── Dim F: Cross-view Safety ──
    joins = list(parsed.find_all(sqlglot.expressions.Join))
    if joins:
        if len(actual_views) > 1 and "v_topics" in actual_views and "v_statements" in actual_views:
            if "topic" in sql_lower or "entity" in sql_lower:
                dim_scores["cross_view"] = 0.0
                dim_details["cross_view"].append("Unnecessary JOIN(s) on table(s) ['v_statements']")
        
        for join in joins:
            join_cond = join.args.get("on")
            if join_cond:
                join_cond_str = str(join_cond).lower()
                if "meeting_id" not in join_cond_str:
                    dim_scores["cross_view"] = 0.0
                    dim_details["cross_view"].append("Hazardous JOIN without 'meeting_id' join condition (potential Cartesian product)")
            else:
                dim_scores["cross_view"] = 0.0
                dim_details["cross_view"].append("Implicit or missing JOIN 'ON' condition")

    # ── Dim G: Anti-patterns ──
    hallucinated_errors = check_hallucinated_columns(parsed)
    if hallucinated_errors:
        dim_scores["anti_patterns"] = 0.0
        dim_details["anti_patterns"].extend(hallucinated_errors)

    scores_list = list(dim_scores.values())
    overall_score = sum(scores_list) / len(scores_list)

    severity = "pass"
    for dim, score in dim_scores.items():
        if score == 0.0:
            severity = "error"
            break
        elif score == 0.5 and severity != "error":
            severity = "warning"

    return {
        "semantic_score": round(overall_score, 2),
        "severity": severity,
        "scores": dim_scores,
        "details": {k: v for k, v in dim_details.items() if v}
    }


# ══════════════════════════════════════════════════════════════════════════════
# Live Execution (requires running PostgreSQL)
# ══════════════════════════════════════════════════════════════════════════════

async def execute_sql(pool: Any, sql: str, user_id: str, timeout_ms: int = 5000) -> tuple[bool, list[dict], str, float]:
    """
    Thực thi SQL trên Read-only transaction.
    Trả (success, rows, error_msg, latency_ms)
    """
    t0 = time.perf_counter()
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SET TRANSACTION READ ONLY")
                await conn.execute(f"SET LOCAL statement_timeout = {timeout_ms}")
                await conn.execute("SELECT set_config('app.current_user_id', $1, true)", user_id)
                rows = await conn.fetch(sql)
        latency_ms = (time.perf_counter() - t0) * 1000
        return True, [dict(r) for r in rows], "", round(latency_ms, 2)
    except Exception as e:
        latency_ms = (time.perf_counter() - t0) * 1000
        return False, [], str(e), round(latency_ms, 2)


# ══════════════════════════════════════════════════════════════════════════════
# Report helpers
# ══════════════════════════════════════════════════════════════════════════════

def _fmt_status(ok: bool) -> str:
    return f"{G}✓ PASS{RS}" if ok else f"{R}✗ FAIL{RS}"


def _print_case(i: int, query: str, result: dict) -> None:
    overall = result["overall_pass"]
    status  = _fmt_status(overall)
    print(f"\n{B}[{i:03d}]{RS} {status} — {CY}{query[:80]}{RS}")

    if not result["syntax_ok"]:
        print(f"       {R}Syntax  : {result['syntax_error']}{RS}")
    if not result["security_ok"]:
        print(f"       {R}Security: {result['security_error']}{RS}")
    if not result["schema_ok"]:
        print(f"       {R}Schema  : {result['schema_error']}{RS}")
    if not result["exec_ok"] and result["exec_error"]:
        print(f"       {R}Exec    : {result['exec_error']}{RS}")
        
    semantic = result.get("semantic_diagnostics", {})
    if semantic:
        score = semantic.get("semantic_score", 1.0)
        severity = semantic.get("severity", "pass")
        color = G if severity == "pass" else (Y if severity == "warning" else R)
        print(f"       Semantic: {color}{severity.upper()} (score: {score:.2f}){RS}")
        
        details = semantic.get("details", {})
        for dim, msgs in details.items():
            for msg in msgs:
                dim_color = Y if severity == "warning" else R
                print(f"         {dim_color}* {dim:<15}: {msg}{RS}")
                
    if result["exec_ok"]:
        row_count = result["row_count"]
        latency   = result["exec_latency_ms"]
        print(f"       {G}Exec OK : {row_count} row(s) in {latency:.1f}ms{RS}")
        ref_views = result.get("referenced_views", [])
        if ref_views:
            print(f"       Views   : {', '.join(ref_views)}")


def _print_radar_chart(scores: dict[str, float]) -> None:
    print(f"\n{B}CAPABILITY RADAR CHART (ASCII):{RS}")
    print(f"  {'-' * 45}")
    for dim, score in scores.items():
        bar_len = int(score * 30)
        bar = "█" * bar_len + "░" * (30 - bar_len)
        percentage = score * 100
        color = G if score >= 0.9 else (Y if score >= 0.7 else R)
        print(f"  {dim:<15} | {color}{bar}{RS} | {color}{percentage:>5.1f}%{RS}")
    print(f"  {'-' * 45}")


def _print_weakness_heatmap(results: list[dict]) -> None:
    print(f"\n{B}WEAKNESS HEATMAP (Errors per View):{RS}")
    print(f"  {'-' * 45}")
    view_issues: dict[str, int] = {}
    view_counts: dict[str, int] = {}
    for r in results:
        ref_views = r.get("referenced_views", [])
        semantic = r.get("semantic_diagnostics", {})
        details = semantic.get("details", {})
        
        for v in ref_views:
            view_counts[v] = view_counts.get(v, 0) + 1
            
        has_issue = any(len(msgs) > 0 for msgs in details.values())
        if has_issue:
            for v in ref_views:
                view_issues[v] = view_issues.get(v, 0) + 1
                
    for view in ALLOWED_VIEWS:
        count = view_counts.get(view, 0)
        issues = view_issues.get(view, 0)
        rate = (issues / count * 100) if count > 0 else 0.0
        
        bar_len = int(rate / 100 * 30)
        bar = "█" * bar_len + "░" * (30 - bar_len)
        
        color = R if rate >= 50 else (Y if rate >= 20 else G)
        print(f"  {view:<18} | {color}{bar}{RS} | {issues}/{count} cases ({color}{rate:.1f}%{RS})")
    print(f"  {'-' * 45}")


def _print_actionable_recommendations(results: list[dict]) -> None:
    print(f"\n{B}ACTIONABLE RECOMMENDATIONS (Prioritized):{RS}")
    print(f"  {'-' * 62}")
    
    hallucinations = 0
    unnecessary_joins = 0
    view_selection_failures = 0
    missing_filters = 0
    aggregation_failures = 0
    missing_distincts = 0
    
    for r in results:
        semantic = r.get("semantic_diagnostics", {})
        details = semantic.get("details", {})
        for dim, msgs in details.items():
            for msg in msgs:
                msg_lower = msg.lower()
                if "hallucinated" in msg_lower:
                    hallucinations += 1
                elif "join" in msg_lower:
                    unnecessary_joins += 1
                elif "selection" in msg_lower:
                    view_selection_failures += 1
                elif "filter" in msg_lower:
                    missing_filters += 1
                elif "aggregation" in msg_lower or "group by" in msg_lower:
                    aggregation_failures += 1
                elif "distinct" in msg_lower:
                    missing_distincts += 1
                    
    recs = []
    if hallucinations > 0:
        recs.append((
            f"{B}{R}[HIGH]{RS} Hallucinated Columns detected ({hallucinations} occurrences)",
            "Update System Prompt with Strict Schema Guards: 'DO NOT reference s.entity or nonexistent fields. Verify against the allowed views definition.'"
        ))
    if unnecessary_joins > 0:
        recs.append((
            f"{B}{R}[HIGH]{RS} Unnecessary JOINs between semantic views ({unnecessary_joins} occurrences)",
            "Provide Few-shot Examples demonstrating distinct view queries and single-view topic search (e.g. source_type = 'entity')."
        ))
    if view_selection_failures > 0:
        recs.append((
            f"{B}{Y}[MEDIUM]{RS} View Selection errors ({view_selection_failures} occurrences)",
            "Enhance routing and context instructions so the model maps keywords to their correct corresponding v_* view."
        ))
    if missing_filters > 0:
        recs.append((
            f"{B}{Y}[MEDIUM]{RS} Missing expected filter conditions ({missing_filters} occurrences)",
            "Add system rules explicitly mapping Japanese words like '未完了' to status='pending' and '完了' to status='done'."
        ))
    if aggregation_failures > 0:
        recs.append((
            f"{B}{Y}[MEDIUM]{RS} Aggregation mismatch / missing GROUP BY ({aggregation_failures} occurrences)",
            "Review dynamic few-shot templates to ensure SUM, COUNT, and breakdown (GROUP BY) structures are perfectly matching."
        ))
    if missing_distincts > 0:
        recs.append((
            f"{B}{CY}[LOW]{RS} Missing DISTINCT or LIMIT clauses ({missing_distincts} occurrences)",
            "Add structural constraints to prompt: 'Use DISTINCT when listing entities/topics, and LIMIT when asking for top results'."
        ))
        
    if not recs:
        print(f"  {G}✓ No semantic issues detected. Your Text2SQL pipeline is in perfect state!{RS}")
    else:
        for title, solution in recs:
            print(f"  * {title}:")
            print(f"    Solution: {solution}\n")
    print(f"  {'-' * 62}")


def _summary_table(results: list[dict]) -> None:
    total      = len(results)
    syn_pass   = sum(1 for r in results if r["syntax_ok"])
    sec_pass   = sum(1 for r in results if r["security_ok"])
    sch_pass   = sum(1 for r in results if r["schema_ok"])
    exec_pass  = sum(1 for r in results if r["exec_ok"])
    sem_pass   = sum(1 for r in results if r.get("semantic_severity") != "error")
    overall    = sum(1 for r in results if r["overall_pass"])

    print(f"\n{B}{CY}{'=' * 62}{RS}")
    print(f"{B}{CY}  EVALUATION SUMMARY — {total} Test Cases{RS}")
    print(f"{B}{CY}{'=' * 62}{RS}")
    print(f"  {'Dimension':<28} {'Pass':>6} {'Fail':>6}  {'Rate':>7}")
    print(f"  {'-'*28} {'-'*6} {'-'*6}  {'-'*7}")

    def row(label, p):
        f = total - p
        rate = p / total * 100
        color = G if rate >= 90 else (Y if rate >= 70 else R)
        return f"  {label:<28} {color}{p:>6}{RS} {R if f else G}{f:>6}{RS}  {color}{rate:>6.1f}%{RS}"

    print(row("1. SQL Syntax Valid",     syn_pass))
    print(row("2. Security Compliant",   sec_pass))
    print(row("3. Schema Correct",       sch_pass))
    print(row("4. Live Execution OK",    exec_pass))
    print(row("5. Semantic Quality OK",  sem_pass))
    print(f"  {'=' * 43}")
    print(row("OVERALL PASS (all 5)",    overall))
    print(f"{B}{CY}{'=' * 62}{RS}")

    failures = [r for r in results if not r["overall_pass"]]
    if failures:
        print(f"\n{B}{R}Failed Cases (including Semantic Errors):{RS}")
        for r in failures:
            reasons = []
            if not r["syntax_ok"]:   reasons.append("Syntax")
            if not r["security_ok"]: reasons.append("Security")
            if not r["schema_ok"]:   reasons.append(f"Schema({r.get('unknown_tables',[])})")
            if not r["exec_ok"]:     reasons.append("Exec")
            if r.get("semantic_severity") == "error": reasons.append("Semantic")
            print(f"  [{r['id']:03d}] {R}{', '.join(reasons)}{RS} — {r['query'][:70]}")

    # Views usage stats
    view_usage: dict[str, int] = {}
    for r in results:
        for v in r.get("referenced_views", []):
            view_usage[v] = view_usage.get(v, 0) + 1

    if view_usage:
        print(f"\n{B}View Coverage:{RS}")
        for view, count in sorted(view_usage.items(), key=lambda x: -x[1]):
            bar = "█" * min(count, 40)
            print(f"  {view:<22} {bar} ({count})")

    # Render advanced radar and heatmaps
    dimensions = ["view_selection", "filter_check", "column_check", "aggregation", "structure", "cross_view", "anti_patterns"]
    dim_totals = {dim: 0.0 for dim in dimensions}
    for r in results:
        semantic = r.get("semantic_diagnostics", {})
        scores = semantic.get("scores", {})
        for dim in dimensions:
            dim_totals[dim] += scores.get(dim, 1.0)
            
    dim_averages = {dim: total_score / total for dim, total_score in dim_totals.items()}
    _print_radar_chart(dim_averages)
    _print_weakness_heatmap(results)
    _print_actionable_recommendations(results)


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

async def run_evaluation(csv_path: Path, db_url: str, user_id: str, verbose: bool) -> list[dict]:
    # Load test cases
    rows = []
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    print(f"{B}{CY}{'=' * 62}{RS}")
    print(f"{B}{CY}  JAVIS TEXT2SQL — TEST CASE EVALUATOR WITH SEMANTIC DIAGNOSTICS{RS}")
    print(f"{B}{CY}  {csv_path.name} — {len(rows)} cases{RS}")
    print(f"{B}{CY}{'=' * 62}{RS}")
    print(f"  DB  : {db_url}")
    print(f"  User: {user_id}")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Create DB pool
    try:
        import asyncpg
        pool = await asyncpg.create_pool(db_url)
        print(f"  DB Status: {G}Connected ✓{RS}\n")
    except Exception as e:
        print(f"  DB Status: {R}FAILED — {e}{RS}\n")
        print(f"{Y}[Warning] Running in STATIC-ONLY mode (no live execution){RS}\n")
        pool = None

    results = []
    for i, row in enumerate(rows, 1):
        query = row.get("query", "").strip()
        sql   = row.get("sql",   "").strip()

        static = static_eval(sql)
        semantic = semantic_eval(query, sql, static)

        # Live execution (only if static passes syntax+security+schema)
        exec_ok     = False
        exec_rows   = []
        exec_error  = ""
        exec_latency = 0.0

        if pool and static["static_pass"]:
            exec_ok, exec_rows, exec_error, exec_latency = await execute_sql(pool, sql, user_id)
        elif pool and not static["static_pass"]:
            exec_error = "Skipped (static check failed)"
        else:
            exec_error = "Skipped (no DB connection)"

        # overall pass now requires live execution, static pass, AND no critical semantic errors
        overall = static["static_pass"] and exec_ok and (semantic["severity"] != "error")

        result = {
            "id":            i,
            "query":         query,
            "sql":           sql,
            "overall_pass":  overall,
            "exec_ok":       exec_ok,
            "exec_error":    exec_error,
            "exec_latency_ms": exec_latency,
            "row_count":     len(exec_rows),
            "semantic_score": semantic["semantic_score"],
            "semantic_severity": semantic["severity"],
            "semantic_diagnostics": semantic,
            **static,
        }
        results.append(result)

        if verbose or not overall:
            _print_case(i, query, result)
        else:
            # Progress dot
            print(f"{G}.{RS}", end="", flush=True)

    if not verbose:
        print()  # newline after dots

    _summary_table(results)

    if pool:
        await pool.close()

    return results


def get_vi_translation(query_ja: str) -> str:
    q = query_ja.strip()
    if "JPY" in q and "総予算" in q:
        return "Tổng ngân sách bằng JPY"
    if "budget" in q and "合計" in q:
        return "Tổng số tiền của các khoản có ngữ cảnh là 'budget'"
    if "すべて" in q and "金額" in q and "通貨" in q:
        return "Liệt kê tất cả số tiền kèm theo loại tiền tệ và ngữ cảnh"
    if "未完了" in q and "コミットメント" in q and "いくつ" in q:
        return "Có bao nhiêu cam kết chưa hoàn thành (pending)?"
    if "完了済み" in q and "コミットメント" in q and "いくつ" in q:
        return "Có bao nhiêu cam kết đã hoàn thành (done)?"
    if "すべて" in q and "コミットメント" in q and "担当者" in q:
        return "Liệt kê tất cả các cam kết kèm người phụ trách, hành động và hạn chót"
    if "2026-06-01より前" in q and "コミットメント" in q:
        return "Liệt kê các cam kết có hạn chót trước ngày 2026-06-01"
    if "2026-05-30より後" in q and "コミットメント" in q:
        return "Liệt kê các cam kết có hạn chót sau ngày 2026-05-30"
    if "重要度スコアが4以上" in q and "アクションアイテム" in q:
        return "Hiển thị các hành động có điểm quan trọng từ 4 trở lên"
    if "未解決の質問" in q and "重要度スコア付き" in q:
        return "Hiển thị tất cả câu hỏi chưa giải quyết kèm điểm quan trọng"
    if "重要度スコアが4以上" in q and "ネガティブな発言" in q:
        return "Hiển thị các phát biểu tiêu cực có điểm quan trọng từ 4 trở lên"
    if "感情別" in q and "発言数" in q:
        return "Đếm số phát biểu theo từng cảm xúc"
    if "VJ" in q and "トピック" in q and "一覧表示" in q:
        return "Liệt kê các chủ đề (topics) của cuộc họp có tiêu đề chứa 'VJ'"
    if "AJ" in q and "トピック" in q and "一覧表示" in q:
        return "Liệt kê các chủ đề (topics) của cuộc họp có tiêu đề chứa 'AJ'"
    if "VJ" in q and "固有エンティティ" in q:
        return "Liệt kê các thực thể định danh (named entities) của cuộc họp có tiêu đề chứa 'VJ'"
    if "AJ" in q and "固有エンティティ" in q:
        return "Liệt kê các thực thể định danh (named entities) của cuộc họp có tiêu đề chứa 'AJ'"
    if "budget" in q and "発言" in q:
        return "Liệt kê các phát biểu đề cập đến 'budget' hoặc 'ngân sách'"
    if "話者ごと" in q and "発話数" in q:
        return "Đếm số phát biểu của mỗi người nói"
    if "VJ Technologies" in q and "発話" in q:
        return "Liệt kê các phát biểu đề cập đến 'VJ Technologies'"
    if "AJ Technologies" in q and "発話" in q:
        return "Liệt kê các phát biểu đề cập đến 'AJ Technologies'"
    if "通貨ごと" in q and "合計" in q:
        return "Tổng số tiền theo từng loại tiền tệ"
    if "会議タイトルごと" in q and "amount_value" in q:
        return "Tổng số tiền theo từng cuộc họp"
    if "JPY" in q and "金額" in q and "一覧表示" in q:
        return "Liệt kê các số tiền có đơn vị là JPY"
    if "budget" in q and "金額" in q and "一覧" in q:
        return "Liệt kê các số tiền có ngữ cảnh chứa 'budget'"
    if "アクションアイテム数" in q and "カウント" in q:
        return "Đếm tổng số hành động cần làm (action items)"
    if "アクションアイテム" in q and "会議日付" in q:
        return "Liệt kê các hành động kèm ngày họp"
    if "ステータスごと" in q and "コミットメント数" in q:
        return "Đếm số cam kết theo từng trạng thái"
    if "Yamashita" in q and "コミットメント" in q:
        return "Liệt kê các cam kết của người phụ trách 'Yamashita'"
    if "Yoshio" in q and "コミットメント" in q:
        return "Liệt kê các cam kết của người phụ trách 'Yoshio'"
    if "日付" in q and "すべて" in q and "一覧表示" in q:
        return "Liệt kê tất cả các ngày được đề cập"
    if "日付" in q and "会議タイトル付き" in q:
        return "Liệt kê các ngày được đề cập kèm tiêu đề cuộc họp"
    if "会議タイトルごと" in q and "日付数" in q:
        return "Đếm số ngày được đề cập theo từng cuộc họp"
    if "Energy" in q and "トピック" in q and "一覧" in q:
        return "Liệt kê các chủ đề (topics) có chứa 'Energy'"
    if "GoEMON" in q and "トピック" in q:
        return "Liệt kê các chủ đề (topics) có chứa 'GoEMON'"
    if "DX" in q and "トピック" in q:
        return "Liệt kê các chủ đề (topics) có chứa 'DX'"
    if "AI" in q and "トピック" in q and "一覧" in q:
        return "Liệt kê các chủ đề (topics) có chứa 'AI'"
    if "budget" in q and "コミットメント" in q:
        return "Liệt kê các cam kết có hành động chứa 'budget'"
    if "budget" in q and "アクションアイテム" in q:
        return "Liệt kê các hành động có chứa 'budget'"
    if "重要度スコアが5以上" in q and "発言" in q:
        return "Liệt kê các phát biểu có điểm quan trọng từ 5 trở lên"
    if "ネガティブ感情" in q:
        return "Liệt kê các phát biểu mang cảm xúc tiêu cực (negative)"
    if "topics" in q and "meeting_id" in q:
        return "Đếm số cuộc họp khác nhau trong bảng topics"
    if "commitments" in q and "meeting_id" in q:
        return "Đếm số cuộc họp khác nhau trong bảng commitments"
    if "topics" in q and "会議タイトルと日付" in q:
        return "Liệt kê tiêu đề và ngày họp từ bảng topics"
    if "commitments" in q and "会議タイトルと日付" in q:
        return "Liệt kê tiêu đề và ngày họp từ bảng commitments"
    if "amounts" in q and "会議タイトルと日付" in q:
        return "Liệt kê tiêu đề và ngày họp từ bảng amounts"
    if "Housing" in q and "発言" in q:
        return "Liệt kê các phát biểu trong các cuộc họp có tiêu đề chứa 'Housing'"
    if "Housing" in q and "コミットメント" in q and "表示" in q:
        return "Hiển thị tất cả cam kết của các cuộc họp có tiêu đề chứa 'Housing'"
    if "Housing" in q and "コミットメント数" in q:
        return "Đếm số cam kết của các cuộc họp có tiêu đề chứa 'Housing'"
    if "Housing" in q and "金額" in q:
        return "Hiển thị số tiền của các cuộc họp có tiêu đề chứa 'Housing'"
    if "entity" in q and "トピック" in q:
        return "Liệt kê các thực thể (source_type = 'entity')"
    if "source_typeごと" in q:
        return "Đếm số chủ đề theo từng loại source_type"
    if "2026-05-26" in q and "トピック" in q:
        return "Liệt kê các chủ đề của cuộc họp ngày 2026-05-26"
    if "2026-05-26" in q and "コミットメント" in q:
        return "Liệt kê các cam kết của cuộc họp ngày 2026-05-26"
    if "2026-05-26" in q and "アクションアイテム" in q:
        return "Liệt kê các hành động của cuộc họp ngày 2026-05-26"
    if "2026-05-26" in q and "未解決質問" in q:
        return "Liệt kê các câu hỏi chưa giải quyết của cuộc họp ngày 2026-05-26"
    if "1000以上" in q and "金額" in q:
        return "Liệt kê các số tiền có giá trị từ 1000 trở lên"
    if "amount_value" in q and "降順" in q:
        return "Liệt kê các khoản tiền sắp xếp giảm dần theo giá trị"
    if "electric" in q and "総金額" in q:
        return "Tổng số tiền của các khoản có ngữ cảnh chứa 'electric'"
    if "budget" in q and "総金額" in q:
        return "Tổng số tiền của các khoản có ngữ cảnh chứa 'budget'"
    if "document" in q and "発話数" in q:
        return "Đếm số phát biểu của người nói 'document'"
    if "異なる話者" in q and "一覧" in q:
        return "Liệt kê các người nói khác nhau"
    if "異なる話者数" in q and "カウント" in q:
        return "Đếm số người nói khác nhau"
    if "Energy Japan" in q and "発話" in q:
        return "Liệt kê các phát biểu đề cập đến 'Energy Japan'"
    if "GoEMON" in q and "発話" in q:
        return "Liệt kê các phát biểu đề cập đến 'GoEMON'"
    if "AI" in q and "発話" in q:
        return "Liệt kê các phát biểu đề cập đến 'AI'"
    if "トピックを会議タイトル付き" in q:
        return "Liệt kê chủ đề kèm theo tiêu đề cuộc họp"
    if "コミットメントを会議タイトルと担当者付き" in q:
        return "Liệt kê cam kết kèm tiêu đề cuộc họp và người phụ trách"
    if "アクションアイテムを会議タイトルとアクションテキスト" in q:
        return "Liệt kê các hành động kèm tiêu đề cuộc họp và văn bản hành động"
    if "未解決質問を会議タイトル" in q:
        return "Liệt kê câu hỏi chưa giải quyết kèm tiêu đề cuộc họp"
    if "会議タイトルごと" in q and "未完了コミットメント数" in q:
        return "Đếm số cam kết chưa hoàn thành (pending) theo từng cuộc họp"
    if "会議タイトルごと" in q and "完了済みコミットメント数" in q:
        return "Đếm số cam kết đã hoàn thành (done) theo từng cuộc họp"
    if "deadline_dateがない" in q:
        return "Liệt kê các cam kết không có ngày hạn chót"
    if "deadline_dateがある" in q:
        return "Liệt kê các cam kết có ngày hạn chót"
    if "confidenceが0.8以上" in q:
        return "Liệt kê các ngày có mức độ tin cậy từ 0.8 trở lên"
    if "confidenceが1.0未満" in q:
        return "Liệt kê các ngày có mức độ tin cậy nhỏ hơn 1.0"
    if "重要度スコアが4以上" in q and "アクションアイテム数" in q:
        return "Đếm số hành động có điểm quan trọng từ 4 trở lên"
    if "重要度スコアが4以上" in q and "未解決質問数" in q:
        return "Đếm số câu hỏi chưa giải quyết có điểm quan trọng từ 4 trở lên"
    if "neutral" in q and "発言" in q:
        return "Liệt kê các phát biểu có cảm xúc trung lập (neutral)"
    if "会議タイトルごと" in q and "発言数" in q:
        return "Đếm số phát biểu theo từng cuộc họp"
    if "会議タイトルごと" in q and "発話数" in q:
        return "Đếm số phát biểu theo từng cuộc họp"
    if "上位5人" in q and "話者" in q:
        return "Liệt kê 5 người nói phát biểu nhiều nhất"
    if "4500" in q:
        return "Liệt kê các phát biểu đề cập đến số tiền 4,500"
    if "man" in q and "amount_value" in q:
        return "Tổng số tiền của các khoản có đơn vị chứa 'man'"
    if "VJ" in q and "金額コンテキストと値" in q:
        return "Liệt kê số tiền và ngữ cảnh của cuộc họp chứa 'VJ'"
    if "VJ Technologies" in q and "会議タイトル" in q:
        return "Liệt kê tiêu đề cuộc họp đề cập đến 'VJ Technologies'"
    if "AJ Technologies" in q and "会議タイトル" in q:
        return "Liệt kê tiêu đề cuộc họp đề cập đến 'AJ Technologies'"
    if "ONE Financial Service" in q and "会議タイトル" in q:
        return "Liệt kê tiêu đề cuộc họp đề cập đến 'ONE Financial Service'"
    if "Energy Japan" in q and "会議タイトル" in q:
        return "Liệt kê tiêu đề cuộc họp đề cập đến 'Energy Japan'"
    if "deadline_date" in q and "昇順" in q:
        return "Sắp xếp cam kết theo thứ tự tăng dần của ngày hạn chót"
    if "this week" in q and "コミットメント" in q:
        return "Liệt kê các cam kết có hạn chót trong tuần này"
    if "アクションアイテム" in q and "重要度スコアの降順" in q:
        return "Sắp xếp các hành động giảm dần theo điểm quan trọng"
    if "未解決質問" in q and "重要度スコアの降順" in q:
        return "Sắp xếp các câu hỏi chưa giải quyết giảm dần theo điểm quan trọng"
    if "発言" in q and "重要度スコアの降順" in q:
        return "Sắp xếp các phát biểu giảm dần theo điểm quan trọng"
    if "会議タイトルごと" in q and "トピック数" in q:
        return "Đếm số chủ đề theo từng cuộc họp"
    if "company profile" in q and "トピック" in q:
        return "Liệt kê các chủ đề (topics) của cuộc họp có tiêu đề chứa 'company profile'"
    if "company profile" in q and "エンティティ" in q:
        return "Liệt kê các thực thể (entities) của cuộc họp có tiêu đề chứa 'company profile'"
    if "summary" in q and "トピック" in q:
        return "Liệt kê các chủ đề (topics) của cuộc họp có tiêu đề chứa 'summary'"
    if "summary" in q and "コミットメント数" in q:
        return "Đếm số cam kết của các cuộc họp có tiêu đề chứa 'summary'"
    if "summary" in q and "金額数" in q:
        return "Đếm số khoản tiền của các cuộc họp có tiêu đề chứa 'summary'"
    return q


def get_vi_evaluation(result: dict) -> tuple[str, str]:
    overall = result.get("overall_pass", False)
    query = result.get("query", "")
    sql = result.get("sql", "")
    sql_lower = sql.lower()
    
    if not result.get("syntax_ok", True):
        err = result.get("syntax_error", "Lỗi cú pháp SQL")
        return "Sai", f"Sai (Lỗi cú pháp SQL: {err})"
        
    if not result.get("security_ok", True):
        err = result.get("security_error", "Vi phạm bảo mật")
        return "Sai", f"Sai (Không tuân thủ bảo mật: {err})"
        
    if not result.get("schema_ok", True):
        err = result.get("schema_error", "Lỗi schema")
        return "Sai", f"Sai (Lỗi schema: {err})"
        
    if not result.get("exec_ok", True):
        err = result.get("exec_error", "Lỗi thực thi SQL")
        return "Sai", f"Sai (Lỗi thực thi: {err})"
        
    semantic_diagnostics = result.get("semantic_diagnostics", {})
    details_list = []
    for dim, details in semantic_diagnostics.get("details", {}).items():
        details_list.extend(details)
        
    for detail in details_list:
        if "Sai" in detail:
            return "Sai", detail
            
    if "総予算" in query and "group by" in sql_lower:
        return "Đúng", "Đúng (GROUP BY amount_currency dư thừa)"
        
    if overall:
        return "Đúng", "Đúng"
        
    if details_list:
        return "Sai", f"Sai (Lỗi ngữ nghĩa: {', '.join(details_list)})"
        
    return "Đúng", "Đúng"


def save_report(results: list[dict], output_path: Path) -> None:
    report = []
    for r in results:
        report.append({
            "id":             r["id"],
            "query":          r["query"],
            "sql":            r["sql"],
            "overall_pass":   r["overall_pass"],
            "syntax_ok":      r["syntax_ok"],
            "syntax_error":   r["syntax_error"],
            "security_ok":    r["security_ok"],
            "security_error": r["security_error"],
            "schema_ok":      r["schema_ok"],
            "schema_error":   r["schema_error"],
            "unknown_tables": r["unknown_tables"],
            "referenced_views": r["referenced_views"],
            "exec_ok":        r["exec_ok"],
            "exec_error":     r["exec_error"],
            "exec_latency_ms": r["exec_latency_ms"],
            "row_count":      r["row_count"],
            "semantic_score": r["semantic_score"],
            "semantic_severity": r["semantic_severity"],
            "semantic_diagnostics": r["semantic_diagnostics"],
        })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{G}Report saved → {output_path}{RS}")

    # Generate Vietnamese Markdown Report
    md_lines = [
        "# BÁO CÁO ĐÁNH GIÁ CHI TIẾT TEXT2SQL (99 TESTCASES)",
        f"*Thời gian thực hiện: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        "*Môi trường kết nối cơ sở dữ liệu: Live PostgreSQL*",
        "",
        "## 1. TỔNG QUAN KẾT QUẢ ĐÁNH GIÁ",
        "| Tiêu chí | Tổng số | Đúng | Sai | Tỷ lệ đạt |",
        "| :--- | :---: | :---: | :---: | :---: |"
    ]
    
    total = len(results)
    passed_cases = []
    failed_cases = []
    for r in results:
        status_label, details = get_vi_evaluation(r)
        if status_label == "Đúng":
            passed_cases.append(r)
        else:
            failed_cases.append((r, details))
            
    pass_count = len(passed_cases)
    fail_count = len(failed_cases)
    rate = (pass_count / total) * 100
    
    md_lines.append(f"| **Đánh giá tổng hợp** | {total} | {pass_count} | {fail_count} | {rate:.1f}% |")
    md_lines.append("")
    md_lines.append("## 2. DANH SÁCH CHI TIẾT CÁC TESTCASE")
    md_lines.append("| ID | Câu hỏi (Tiếng Nhật) | Câu dịch (Tiếng Việt) | Đánh giá | Trạng thái | Chi tiết đánh giá |")
    md_lines.append("| :---: | :--- | :--- | :---: | :---: | :--- |")
    
    for r in results:
        vi_trans = get_vi_translation(r["query"])
        status_label, details = get_vi_evaluation(r)
        status_badge = "✅ Đúng" if status_label == "Đúng" else "❌ Sai"
        md_lines.append(f"| {r['id']} | {r['query']} | {vi_trans} | {status_label} | {status_badge} | {details} |")
        
    md_path = output_path.parent / "danh_gia_chi_tiet.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"{G}Markdown report saved → {md_path}{RS}")

    # Generate Premium Dark Glassmorphism HTML Dashboard
    html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Javis Text2SQL - Báo cáo Đánh giá Chi tiết</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-color: #0b0f19;
            --card-bg: rgba(17, 25, 40, 0.65);
            --border-color: rgba(255, 255, 255, 0.08);
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
            --primary: #8b5cf6;
            --primary-glow: rgba(139, 92, 246, 0.15);
            --accent: #06b6d4;
            --success: #10b981;
            --success-glow: rgba(16, 185, 129, 0.15);
            --danger: #ef4444;
            --danger-glow: rgba(239, 68, 68, 0.15);
            --warning: #f59e0b;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            background-color: var(--bg-color);
            background-image: 
                radial-gradient(at 0% 0%, rgba(139, 92, 246, 0.15) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(6, 182, 212, 0.15) 0px, transparent 50%);
            background-attachment: fixed;
            color: var(--text-main);
            font-family: 'Plus Jakarta Sans', sans-serif;
            line-height: 1.6;
            padding: 2rem;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}

        header {{
            margin-bottom: 2.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .logo-area h1 {{
            font-size: 2rem;
            font-weight: 700;
            letter-spacing: -0.025em;
            background: linear-gradient(135deg, #fff 0%, #a78bfa 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.25rem;
        }}

        .logo-area p {{
            color: var(--text-muted);
            font-size: 0.95rem;
        }}

        .timestamp {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            padding: 0.5rem 1rem;
            border-radius: 12px;
            font-size: 0.85rem;
            color: var(--text-muted);
            backdrop-filter: blur(12px);
        }}

        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2.5rem;
        }}

        .metric-card {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            padding: 1.75rem;
            backdrop-filter: blur(12px);
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
            position: relative;
            overflow: hidden;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }}

        .metric-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 4px;
            height: 100%;
        }}

        .metric-card.total::before {{ background: var(--primary); }}
        .metric-card.success::before {{ background: var(--success); }}
        .metric-card.danger::before {{ background: var(--danger); }}
        .metric-card.rate::before {{ background: var(--accent); }}

        .metric-card:hover {{
            transform: translateY(-4px);
            border-color: rgba(255, 255, 255, 0.15);
            box-shadow: 0 12px 40px 0 rgba(0, 0, 0, 0.5);
        }}

        .metric-label {{
            font-size: 0.9rem;
            color: var(--text-muted);
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.5rem;
        }}

        .metric-value {{
            font-size: 2.25rem;
            font-weight: 700;
            margin-bottom: 0.25rem;
        }}

        .metric-desc {{
            font-size: 0.85rem;
            color: var(--text-muted);
        }}

        .controls {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 20px;
            padding: 1.25rem;
            margin-bottom: 2rem;
            backdrop-filter: blur(12px);
            display: flex;
            flex-wrap: wrap;
            gap: 1rem;
            align-items: center;
            justify-content: space-between;
        }}

        .search-wrapper {{
            position: relative;
            flex: 1;
            min-width: 300px;
        }}

        .search-input {{
            width: 100%;
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 0.75rem 1rem;
            color: var(--text-main);
            font-family: inherit;
            font-size: 0.95rem;
            transition: all 0.2s ease;
        }}

        .search-input:focus {{
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px var(--primary-glow);
        }}

        .filter-buttons {{
            display: flex;
            gap: 0.5rem;
        }}

        .filter-btn {{
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--border-color);
            color: var(--text-muted);
            padding: 0.6rem 1.2rem;
            border-radius: 10px;
            font-family: inherit;
            font-size: 0.9rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
        }}

        .filter-btn:hover {{
            background: rgba(255, 255, 255, 0.1);
            color: var(--text-main);
        }}

        .filter-btn.active {{
            background: var(--primary);
            color: #fff;
            border-color: var(--primary);
            box-shadow: 0 0 12px var(--primary-glow);
        }}

        .table-card {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 24px;
            overflow: hidden;
            backdrop-filter: blur(12px);
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        }}

        .table-responsive {{
            overflow-x: auto;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
        }}

        th {{
            background: rgba(0, 0, 0, 0.2);
            padding: 1.2rem 1.5rem;
            font-size: 0.85rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            border-bottom: 1px solid var(--border-color);
        }}

        td {{
            padding: 1.25rem 1.5rem;
            border-bottom: 1px solid var(--border-color);
            font-size: 0.95rem;
            vertical-align: top;
        }}

        tr {{
            transition: background-color 0.2s ease;
        }}

        tr:hover td {{
            background-color: rgba(255, 255, 255, 0.02);
        }}

        .case-id {{
            font-weight: 700;
            color: var(--text-muted);
        }}

        .question-col {{
            max-width: 320px;
        }}

        .ja-text {{
            font-weight: 500;
            margin-bottom: 0.4rem;
        }}

        .vi-text {{
            color: var(--text-muted);
            font-size: 0.85rem;
            background: rgba(255, 255, 255, 0.03);
            padding: 0.4rem 0.6rem;
            border-radius: 6px;
            display: inline-block;
        }}

        .sql-code {{
            font-family: 'Courier New', Courier, monospace;
            font-size: 0.85rem;
            background: rgba(0, 0, 0, 0.4);
            padding: 0.6rem 0.8rem;
            border-radius: 8px;
            border: 1px solid var(--border-color);
            color: #c084fc;
            white-space: pre-wrap;
            word-break: break-all;
            max-width: 450px;
        }}

        .badge {{
            display: inline-flex;
            align-items: center;
            padding: 0.35rem 0.85rem;
            border-radius: 99px;
            font-size: 0.8rem;
            font-weight: 600;
        }}

        .badge-success {{
            background: var(--success-glow);
            color: var(--success);
            border: 1px solid rgba(16, 185, 129, 0.2);
        }}

        .badge-danger {{
            background: var(--danger-glow);
            color: var(--danger);
            border: 1px solid rgba(239, 68, 68, 0.2);
        }}

        .diagnostic-text {{
            font-size: 0.85rem;
            font-weight: 500;
        }}

        .diagnostic-text.fail-reason {{
            color: #fda4af;
            background: rgba(239, 68, 68, 0.08);
            padding: 0.5rem 0.75rem;
            border-radius: 8px;
            border: 1px solid rgba(239, 68, 68, 0.15);
            max-width: 350px;
        }}

        .diagnostic-text.pass-details {{
            color: var(--text-muted);
        }}

        .diagnostic-text.warning-details {{
            color: #fcd34d;
            background: rgba(245, 158, 11, 0.08);
            padding: 0.5rem 0.75rem;
            border-radius: 8px;
            border: 1px solid rgba(245, 158, 11, 0.15);
            max-width: 350px;
        }}

        @media (max-width: 1024px) {{
            body {{ padding: 1rem; }}
            .controls {{ flex-direction: column; align-items: stretch; }}
            .search-wrapper {{ min-width: 100%; }}
            .filter-buttons {{ justify-content: center; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="logo-area">
                <h1>Javis Text2SQL</h1>
                <p>Báo cáo Đánh giá Chất lượng Ngữ nghĩa và Thừa hành</p>
            </div>
            <div class="timestamp">
                Thời gian quét: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            </div>
        </header>

        <section class="metrics-grid">
            <div class="metric-card total">
                <div class="metric-label">Tổng số Test Cases</div>
                <div class="metric-value">{total}</div>
                <div class="metric-desc">Tập kiểm thử tiêu chuẩn javis-text2sql</div>
            </div>
            <div class="metric-card success">
                <div class="metric-label font-bold">Số lượng Đúng</div>
                <div class="metric-value" style="color: var(--success);">{pass_count}</div>
                <div class="metric-desc">Vượt qua các kiểm tra cú pháp, schema và nghiệp vụ</div>
            </div>
            <div class="metric-card danger">
                <div class="metric-label font-bold">Số lượng Sai</div>
                <div class="metric-value" style="color: var(--danger);">{fail_count}</div>
                <div class="metric-desc">Phát hiện lỗi logic hoặc lệch chuẩn cơ sở dữ liệu</div>
            </div>
            <div class="metric-card rate">
                <div class="metric-label">Tỷ lệ chính xác</div>
                <div class="metric-value" style="color: var(--accent);">{rate:.1f}%</div>
                <div class="metric-desc">Chỉ số chất lượng mô hình hiện tại</div>
            </div>
        </section>

        <section class="controls">
            <div class="search-wrapper">
                <input type="text" id="searchInput" class="search-input" placeholder="Tìm kiếm theo ID, Câu hỏi, SQL hoặc lý do lỗi...">
            </div>
            <div class="filter-buttons">
                <button class="filter-btn active" onclick="filterTable('all', this)">Tất cả ({total})</button>
                <button class="filter-btn" style="color: var(--success);" onclick="filterTable('pass', this)">Đúng ({pass_count})</button>
                <button class="filter-btn" style="color: var(--danger);" onclick="filterTable('fail', this)">Sai ({fail_count})</button>
            </div>
        </section>

        <section class="table-card">
            <div class="table-responsive">
                <table id="evaluationTable">
                    <thead>
                        <tr>
                            <th style="width: 5%;">ID</th>
                            <th style="width: 30%;">Câu hỏi & Bản dịch</th>
                            <th style="width: 35%;">Truy vấn SQL Kiểm thử</th>
                            <th style="width: 10%; text-align: center;">Trạng thái</th>
                            <th style="width: 20%;">Chi tiết đánh giá</th>
                        </tr>
                    </thead>
                    <tbody>
    """
    
    for r in results:
        vi_trans = get_vi_translation(r["query"])
        status_label, details = get_vi_evaluation(r)
        
        status_class = "badge-success" if status_label == "Đúng" else "badge-danger"
        status_text = "Đúng" if status_label == "Đúng" else "Sai"
        
        detail_class = "pass-details"
        if status_label == "Sai":
            detail_class = "fail-reason"
        elif "dư thừa" in details:
            detail_class = "warning-details"
            
        html_content += f"""
                        <tr class="testcase-row" data-status="{"pass" if status_label == "Đúng" else "fail"}">
                            <td class="case-id">#{r["id"]}</td>
                            <td class="question-col">
                                <div class="ja-text">{r["query"]}</div>
                                <div class="vi-text">{vi_trans}</div>
                            </td>
                            <td>
                                <pre class="sql-code"><code>{r["sql"]}</code></pre>
                            </td>
                            <td style="text-align: center;">
                                <span class="badge {status_class}">{status_text}</span>
                            </td>
                            <td>
                                <div class="diagnostic-text {detail_class}">{details}</div>
                            </td>
                        </tr>
        """
        
    html_content += """
                    </tbody>
                </table>
            </div>
        </section>
    </div>

    <script>
        function filterTable(status, btnElement) {
            // Update active state of filter buttons
            const buttons = document.querySelectorAll('.filter-btn');
            buttons.forEach(btn => btn.classList.remove('active'));
            btnElement.classList.add('active');

            // Filter table rows
            const rows = document.querySelectorAll('.testcase-row');
            rows.forEach(row => {
                const rowStatus = row.getAttribute('data-status');
                if (status === 'all' || rowStatus === status) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        }

        // Live text searching
        document.getElementById('searchInput').addEventListener('input', function(e) {
            const query = e.target.value.toLowerCase().trim();
            const rows = document.querySelectorAll('.testcase-row');
            
            // Clear active filter button to show search across all
            if (query !== '') {
                const buttons = document.querySelectorAll('.filter-btn');
                buttons.forEach(btn => btn.classList.remove('active'));
                buttons[0].classList.add('active');
            }

            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                if (text.includes(query)) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        });
    </script>
</body>
</html>
"""

    html_path = output_path.parent / "danh_gia_chi_tiet.html"
    html_path.write_text(html_content, encoding="utf-8")
    print(f"{G}HTML report dashboard saved → {html_path}{RS}")


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    import argparse
    from javis_text2sql.config import Settings

    parser = argparse.ArgumentParser(description="Javis Text2SQL Test Case Evaluator")
    parser.add_argument("--csv",     default="testcase-text2sql.csv",  help="Path to test case CSV")
    parser.add_argument("--output",  default="reports/eval_testcases.json", help="JSON report output path")
    parser.add_argument("--user-id", default="00000000-0000-0000-0000-000000000000", help="Tenant user_id for RLS")
    parser.add_argument("--verbose", action="store_true", help="Print every test case (not just failures)")
    args = parser.parse_args()

    settings = Settings.from_env()
    db_url   = settings.database_url or ""
    if not db_url:
        print(f"{R}[ERROR] TEXT2SQL_DATABASE_URL is not set in .env{RS}")
        sys.exit(1)

    csv_path    = Path(args.csv)
    output_path = Path(args.output)

    results = asyncio.run(run_evaluation(csv_path, db_url, args.user_id, args.verbose))
    save_report(results, output_path)
