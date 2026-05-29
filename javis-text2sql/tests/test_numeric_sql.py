from __future__ import annotations

import pytest
from datetime import date, timedelta
from typing import Any
from javis_text2sql.query.numeric_sql import (
    heuristic_numeric_intent,
    resolve_relative_date,
    run_numeric_sql,
    NumericIntent,
    NumericResult
)


@pytest.fixture
def ref_date() -> date:
    return date(2026, 5, 29)  # Friday


# 3a. Positive cases — NÊN intercept
@pytest.mark.parametrize(
    "query,expected_op,expected_target,expected_group",
    [
        ("今月の会議の合計時間は？", "sum", "duration_seconds", "none"),
        ("先週、何件の会議がありましたか？", "count", "meeting_count", "none"),
        ("最も長かった会議は？", "max", "duration_seconds", "none"),
        ("一番短い会議は？", "min", "duration_seconds", "none"),
        ("会議の平均所要時間は？", "avg", "duration_seconds", "none"),
        ("今月、日ごとに何件 of 会議がありましたか？", "count", "meeting_count", "day"),
        ("話者ごとの会議数は？", "count", "meeting_count", "speaker"),
        ("昨日、何か会議はありましたか？", "count", "meeting_count", "none"),
        ("5月の会議は合計何時間？", "sum", "duration_seconds", "none"),
        ("ミーティングは何件ありましたか？", "count", "meeting_count", "none"),
    ],
)
def test_heuristic_positive_cases(
    query: str,
    expected_op: str,
    expected_target: str,
    expected_group: str,
    ref_date: date
):
    intent = heuristic_numeric_intent(query, ref_date)
    assert intent.operator == expected_op
    assert intent.target == expected_target
    assert intent.group_by == expected_group


# 3b. Negative cases — KHÔNG ĐƯỢC intercept (CRITICAL)
@pytest.mark.parametrize(
    "query",
    [
        "未完了のタスクは何件ありますか？",
        "コミットメントはいくつ？",
        "アクションアイテムの件数は？",
        "質問はいくつ未解決ですか？",
        "予算の合計はいくら？",
        "トピックはいくつありますか？",
        "佐藤さんは何分頃に発言しましたか？",
        "AJ Technologiesとは？",
        "すべての会議の一覧を表示してください。",
        "会議のリストを見せて。",
        "昨日の打ち合わせの詳細",
        "会議のアジェンダは何ですか？",
        "先週のミーティングの議事録",
        "本日の打ち合わせ内容",
    ],
)
def test_heuristic_negative_cases(query: str, ref_date: date):
    intent = heuristic_numeric_intent(query, ref_date)
    assert intent.operator == "skip"
    assert intent.target == "none"


# Test date resolving
def test_resolve_relative_date(ref_date: date):
    # Friday, 2026-05-29
    # This week: Monday 2026-05-25 to Sunday 2026-05-31
    # Last week: Monday 2026-05-18 to Sunday 2026-05-24

    # yesterday
    d1, d2 = resolve_relative_date("昨日の会議", ref_date)
    assert d1 == date(2026, 5, 28)
    assert d2 == date(2026, 5, 28)

    # today
    d1, d2 = resolve_relative_date("今日の会議", ref_date)
    assert d1 == date(2026, 5, 29)
    assert d2 == date(2026, 5, 29)

    # tomorrow
    d1, d2 = resolve_relative_date("明日", ref_date)
    assert d1 == date(2026, 5, 30)
    assert d2 == date(2026, 5, 30)

    # this week
    d1, d2 = resolve_relative_date("今週の会議", ref_date)
    assert d1 == date(2026, 5, 25)
    assert d2 == date(2026, 5, 31)

    # last week
    d1, d2 = resolve_relative_date("先週の会議", ref_date)
    assert d1 == date(2026, 5, 18)
    assert d2 == date(2026, 5, 24)

    # this month
    d1, d2 = resolve_relative_date("今月の会議", ref_date)
    assert d1 == date(2026, 5, 1)
    assert d2 == date(2026, 5, 31)

    # last month
    d1, d2 = resolve_relative_date("先月", ref_date)
    assert d1 == date(2026, 4, 1)
    assert d2 == date(2026, 4, 30)

    # specific month
    d1, d2 = resolve_relative_date("12月の会議", ref_date)
    assert d1 == date(2026, 12, 1)
    assert d2 == date(2026, 12, 31)


class MockConn:
    def __init__(self) -> None:
        self.executed_queries: list[str] = []
        self.executed_params: list[tuple] = []

    def transaction(self):
        class MockTransaction:
            async def __aenter__(self) -> MockTransaction:
                return self
            async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
                pass
        return MockTransaction()

    async def execute(self, query: str, *args: Any) -> str:
        self.executed_queries.append(query)
        self.executed_params.append(args)
        return "OK"

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        self.executed_queries.append(query)
        self.executed_params.append(args)
        if "ARRAY_AGG(DISTINCT t.speaker)" in query:
            return [{
                "meeting_id": "test-meeting-uuid",
                "title": "Test Title",
                "meeting_date": "2026-05-29",
                "value": 1800,
                "summary": "Meeting Summary",
                "participants": ["Alice", "Bob"]
            }]
        elif "GROUP BY" in query:
            return [{"group_key": "Alice", "value": 10.0}]
        elif "m.id::text AS meeting_id" in query:
            return [{"meeting_id": "test-meeting-uuid"}]
        elif "value" in query:
            return [{"value": 5.0}]
        return []


# 3c. SQL execution tests — mock asyncpg conn
@pytest.mark.asyncio
async def test_run_numeric_sql_execution():
    conn = MockConn()
    intent = NumericIntent(
        operator="count",
        target="meeting_count",
        group_by="speaker",
        date_start=date(2026, 5, 1),
        date_end=date(2026, 5, 31)
    )
    user_id = "11111111-1111-1111-1111-111111111111"
    
    result = await run_numeric_sql(conn, intent, user_id)
    
    assert isinstance(result, NumericResult)
    assert result.operator == "count"
    assert result.target == "meeting_count"
    assert len(result.rows) == 1
    assert result.rows[0].group_key == "Alice"
    assert result.rows[0].value == 10.0
    assert result.source_meeting_ids == ["test-meeting-uuid"]

    # Verify RLS and readonly configs were set
    assert any("SET TRANSACTION READ ONLY" in q for q in conn.executed_queries)
    assert any("SET LOCAL statement_timeout" in q for q in conn.executed_queries)
    assert any("set_config('app.current_user_id'" in q for q in conn.executed_queries)
    
    # Check that schema matches: m.user_id, FROM meetings m, FROM turns
    group_sql = [q for q in conn.executed_queries if "GROUP BY" in q][0]
    assert "FROM meetings m" in group_sql
    assert "turns" in group_sql
    assert "chunks_turn" not in group_sql
    assert "transcripts" not in group_sql


@pytest.mark.asyncio
async def test_run_duration_extreme_execution():
    conn = MockConn()
    intent = NumericIntent(
        operator="max",
        target="duration_seconds",
        group_by="none",
        date_start=date(2026, 5, 1),
        date_end=date(2026, 5, 31)
    )
    user_id = "11111111-1111-1111-1111-111111111111"
    
    result = await run_numeric_sql(conn, intent, user_id)
    
    assert result.operator == "max"
    assert result.target == "duration_seconds"
    assert result.rows[0].value == 1800.0
    assert result.rows[0].metadata["meeting_id"] == "test-meeting-uuid"
    assert result.rows[0].metadata["participants"] == ["Alice", "Bob"]
    assert result.source_meeting_ids == ["test-meeting-uuid"]

    extreme_sql = conn.executed_queries[3]  # index 3 is duration extreme
    assert "ARRAY_AGG(DISTINCT t.speaker)" in extreme_sql
    assert "FROM meetings m" in extreme_sql
    assert "ORDER BY m.duration_seconds DESC" in extreme_sql


@pytest.mark.asyncio
async def test_pipeline_integration_numeric_intercept():
    from javis_text2sql.llm.fixture import FixtureLLMClient
    from javis_text2sql.query.pipeline import text2sql_pipeline
    
    conn = MockConn()
    llm = FixtureLLMClient(generated_sql=["SHOULD_NOT_BE_CALLED"])
    
    class MockAcquire:
        def __init__(self, conn_obj):
            self.conn = conn_obj
        async def __aenter__(self):
            return self.conn
        async def __aexit__(self, exc_type, exc, tb):
            pass

    class MockPool:
        def __init__(self, conn_obj: MockConn) -> None:
            self.conn = conn_obj
        def acquire(self):
            return MockAcquire(self.conn)

    result = await text2sql_pipeline(
        "今月の会議は何件ありましたか？",
        MockPool(conn),
        llm,
        date(2026, 5, 29)
    )
    
    assert result.success
    assert "meetings m" in result.sql
    assert result.data == [{"group_key": None, "value": 5.0, "metadata": {}}]
    assert not llm.generate_calls


@pytest.mark.asyncio
async def test_pipeline_integration_non_meeting_fallback():
    from javis_text2sql.llm.fixture import FixtureLLMClient
    from javis_text2sql.query.pipeline import text2sql_pipeline
    
    conn = MockConn()
    llm = FixtureLLMClient(generated_sql=["SELECT COUNT(1) AS answer FROM v_commitments;"])
    
    class MockAcquire:
        def __init__(self, conn_obj):
            self.conn = conn_obj
        async def __aenter__(self):
            return self.conn
        async def __aexit__(self, exc_type, exc, tb):
            pass

    class MockPool:
        def __init__(self, conn_obj: MockConn) -> None:
            self.conn = conn_obj
        def acquire(self):
            return MockAcquire(self.conn)

    result = await text2sql_pipeline(
        "コミットメントを数えてください",
        MockPool(conn),
        llm,
        date(2026, 5, 29)
    )
    
    assert result.success
    assert "v_commitments" in result.sql
    assert len(llm.generate_calls) > 0

