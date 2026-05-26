from __future__ import annotations

from datetime import date

from javis_text2sql.query.prompt import FEW_SHOT_EXAMPLES, build_sql_system_prompt
from javis_text2sql.query.sql_validation import clean_sql_markdown, validate_sql
from javis_text2sql.routing.router import route_question


def test_router_classifies_sql_rag_and_hybrid() -> None:
    assert route_question("Tổng ngân sách là bao nhiêu?").route == "sql"
    assert route_question("Tóm tắt cuộc họp này").route == "rag"
    assert route_question("Cuộc họp quyết định gì về ngân sách và con số cụ thể là bao nhiêu?").route == "hybrid"
    assert route_question("予算に関する金額を合計してください。").route == "sql"


def test_prompt_contains_exactly_15_few_shot_examples_and_allowed_views() -> None:
    assert len(FEW_SHOT_EXAMPLES) == 15
    prompt = build_sql_system_prompt(date(2026, 5, 26), {"AJ": "AJ Technologies"})
    assert "Today's reference date: 2026-05-26" in prompt
    assert "v_commitments" in prompt
    assert "AJ => AJ Technologies" in prompt


def test_sql_cleaning_and_validation() -> None:
    assert clean_sql_markdown("```sql\nSELECT * FROM v_topics;\n```") == "SELECT * FROM v_topics;"
    assert validate_sql("SELECT * FROM v_commitments;").ok
    assert validate_sql("SELECT SUM(amount_value) FROM v_amounts;").ok
    assert not validate_sql("SELECT * FROM commitments;").ok
    assert not validate_sql("DELETE FROM commitments;").ok
    assert not validate_sql("SELECT * FROM v_topics; DROP TABLE meetings;").ok
