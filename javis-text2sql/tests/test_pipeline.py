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

    async def execute(self, query: str) -> str:
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
    llm = FixtureLLMClient(generated_sql=["SELECT COUNT(*) AS answer FROM v_commitments;"])
    result = await text2sql_pipeline("Đếm cam kết", FakePool(conn), llm, date(2026, 5, 26))

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
        refined_sql=["SELECT COUNT(*) AS answer FROM v_commitments;"],
    )
    result = await text2sql_pipeline("Đếm cam kết", FakePool(conn), llm, date(2026, 5, 26))

    assert result.success
    assert result.retry_used
    assert result.sql == "SELECT COUNT(*) AS answer FROM v_commitments;"
    assert conn.execution_count == 2
