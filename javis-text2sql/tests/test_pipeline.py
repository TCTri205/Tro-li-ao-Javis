from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from javis_text2sql.llm.fixture import FixtureLLMClient
from javis_text2sql.query.pipeline import text2sql_pipeline


class FakeTransaction:
    async def __aenter__(self) -> "FakeTransaction":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


class FakeAcquire:
    def __init__(self, conn: "FakeConn") -> None:
        self.conn = conn

    async def __aenter__(self) -> "FakeConn":
        return self.conn

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


class FakeConn:
    def __init__(self, fail_first_execution: bool = False) -> None:
        self.fail_first_execution = fail_first_execution
        self.execution_count = 0
        self.executed: list[str] = []

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()

    async def execute(self, query: str, *args: Any) -> str:
        self.executed.append(query)
        return "OK"

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        if "FROM entity_aliases" in query:
            return [{"alias": "AJ", "canonical_name": "AJ Technologies"}]
        self.execution_count += 1
        if self.fail_first_execution and self.execution_count == 1:
            raise RuntimeError("column does not exist")
        return [{"answer": 1}]


class FakePool:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn

    def acquire(self) -> FakeAcquire:
        return FakeAcquire(self.conn)


@pytest.mark.asyncio
async def test_pipeline_success_path_uses_readonly_transaction() -> None:
    conn = FakeConn()
    llm = FixtureLLMClient(generated_sql=["SELECT COUNT(1) AS answer FROM v_commitments;"])
    result = await text2sql_pipeline("コミットメントを数えてください", FakePool(conn), llm, date(2026, 5, 26))

    assert result.success
    assert result.data == [{"answer": 1}]
    assert result.retry_used is False
    assert "SET TRANSACTION READ ONLY" in conn.executed


@pytest.mark.asyncio
async def test_pipeline_rejects_unsafe_sql_before_execution() -> None:
    conn = FakeConn()
    llm = FixtureLLMClient(generated_sql=["DELETE FROM commitments;"])
    result = await text2sql_pipeline("bad", FakePool(conn), llm, date(2026, 5, 26))

    assert not result.success
    assert "Security validation failed" in (result.error or "")
    assert conn.execution_count == 0


@pytest.mark.asyncio
async def test_pipeline_retries_once_after_execution_error() -> None:
    conn = FakeConn(fail_first_execution=True)
    llm = FixtureLLMClient(
        generated_sql=["SELECT missing_column FROM v_commitments;"],
        refined_sql=["SELECT COUNT(1) AS answer FROM v_commitments;"],
    )
    result = await text2sql_pipeline("コミットメントを数えてください", FakePool(conn), llm, date(2026, 5, 26))

    assert result.success
    assert result.retry_used
    assert result.sql == "SELECT COUNT(1) AS answer FROM v_commitments;"
    assert conn.execution_count == 2


@pytest.mark.asyncio
async def test_map_entities_advanced_japanese_normalization() -> None:
    from javis_text2sql.query.pipeline import map_entities
    
    class MockConn:
        async def fetch(self, query: str, *args: Any) -> list[dict[str, str]]:
            return [
                {"alias": "VJ Technologies", "canonical_name": "VJ Technologies"},
                {"alias": "Energy Japan", "canonical_name": "Energy Japan"},
                {"alias": "代表取締役", "canonical_name": "Representative Director"},
            ]
            
    conn = MockConn()
    
    res1 = await map_entities("ＶＪ　Ｔｅｃｈｎｏｌｏｇｉｅｓについて教えて", conn)
    assert "VJ Technologies" in res1
    
    res2 = await map_entities("Energy Japaの情報をください", conn)
    assert "Energy Japan" in res2
    
    res3 = await map_entities("代表取締役は誰ですか？", conn)
    assert "代表取締役" in res3


def test_temporal_date_resolution_context() -> None:
    from javis_text2sql.query.pipeline import generate_temporal_context
    ref = date(2026, 5, 26)  # Tuesday
    context = generate_temporal_context(ref)
    
    assert "2026-05-26" in context  # Today
    assert "2026-05-25" in context  # Yesterday
    assert "2026-05-27" in context  # Tomorrow
    assert "2026-05-24" in context  # Start of this week (Sunday or Monday)
    assert "2026-05-01" in context  # Start of this month
    assert "2026-05-31" in context  # End of this month


def test_redis_cache_layer_behavior() -> None:
    from unittest.mock import MagicMock
    from javis_text2sql.query.pipeline import RedisCache, Text2SQLResult

    # 1. Graceful fallback on connection error
    cache_no_redis = RedisCache("redis://invalid_host:12345/0")
    assert not cache_no_redis._is_available
    assert cache_no_redis.get("test", "user", date(2026, 5, 26)) is None

    # 2. Cache HIT / SET behavior when Redis is available
    mock_client = MagicMock()
    mock_client.ping.return_value = True
    mock_client.get.return_value = b'{"success": true, "sql": "SELECT 1;", "data": [{"val": 1}]}'

    cache = RedisCache()
    cache._client = mock_client
    cache._is_available = True

    # Test cache GET
    res = cache.get("test query", "user_123", date(2026, 5, 26))
    assert res is not None
    assert res.success
    assert res.sql == "SELECT 1;"
    assert res.data == [{"val": 1}]

    # Test cache SET
    pipeline_res = Text2SQLResult(success=True, sql="SELECT 2;", data=[{"val": 2}])
    cache.set("new query", "user_123", date(2026, 5, 26), pipeline_res)
    mock_client.setex.assert_called_once()


@pytest.mark.asyncio
async def test_dynamic_few_shot_retrieval_fallback() -> None:
    from javis_text2sql.query.pipeline import retrieve_few_shots
    from javis_text2sql.query.prompt import FEW_SHOT_EXAMPLES

    class MockConnEmpty:
        async def fetchval(self, query: str) -> Any:
            return False  # Golden queries table does not exist
        async def fetch(self, query: str, *args: Any) -> list[Any]:
            return []

    conn = MockConnEmpty()
    shots = await retrieve_few_shots("some question", conn, limit=3)
    assert len(shots) == 3
    assert shots == FEW_SHOT_EXAMPLES[:3]

