from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from javis_text2sql.etl.loader import load_meeting
from javis_text2sql.etl.models import MeetingMeta
from javis_text2sql.llm.fixture import FixtureLLMClient


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
    def __init__(self) -> None:
        self.fetchval_calls: list[tuple[str, tuple[Any, ...]]] = []
        self.executemany_calls: list[tuple[str, list[tuple[Any, ...]]]] = []
        self.next_id = 0

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()

    async def fetchval(self, query: str, *args: Any) -> str:
        self.fetchval_calls.append((query, args))
        self.next_id += 1
        return f"id-{self.next_id}"

    async def execute(self, query: str, *args: Any) -> str:
        return "OK"

    async def executemany(self, query: str, rows: list[tuple[Any, ...]]) -> None:
        self.executemany_calls.append((query, rows))


class FakePool:
    def __init__(self) -> None:
        self.conn = FakeConn()

    def acquire(self) -> FakeAcquire:
        return FakeAcquire(self.conn)


@pytest.mark.asyncio
async def test_load_meeting_inserts_meeting_passages_turns_and_commitments() -> None:
    raw = """
•総予算（土地・建物・諸費用）上限：約４,５００万円。
•当社は総額４,５００万円内に収まりそうな土地を３〜４件選定し、今週金曜までにメールへ送付する。
•資金計画書は次回までに作成する。
"""
    pool = FakePool()
    meta = MeetingMeta(
        title="sample",
        meeting_date=date(2026, 5, 26),
        speaker_count=1,
        duration_seconds=0,
        summary="sample",
        source_language="ja",
    )
    meeting_id = await load_meeting(raw, meta, pool, FixtureLLMClient(), max_turns=10)

    assert meeting_id == "id-1"
    assert len(pool.conn.fetchval_calls) == 2
    commitment_insert = [call for call in pool.conn.executemany_calls if "INSERT INTO commitments" in call[0]]
    turn_insert = [call for call in pool.conn.executemany_calls if "INSERT INTO turns" in call[0]]
    assert commitment_insert
    assert len(commitment_insert[0][1]) >= 1
    assert turn_insert
    assert len(turn_insert[0][1]) == 3
    first_row = turn_insert[0][1][0]
    assert len(first_row) == 7
    embedding_str = first_row[6]
    assert embedding_str is not None
    assert embedding_str.startswith("[")
    assert embedding_str.endswith("]")
