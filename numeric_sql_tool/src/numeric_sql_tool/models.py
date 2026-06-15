from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class NumericIntent(BaseModel):
    operator: Literal["sum", "avg", "max", "min", "count", "skip", "none"] = "none"
    target: Literal["duration_seconds", "meeting_count", "time_start_sec", "speaking_time", "turn_count", "mention_count", "none"] = "none"
    group_by: Literal["none", "user_id", "day", "week", "month", "speaker"] = "none"
    context_filter: str | None = None
    speaker: str | None = None
    keyword: str | None = None
    limit: int = 1


class NumericRow(BaseModel):
    group_key: str | None = None
    value: float
    metadata: dict = Field(default_factory=dict)


class NumericResult(BaseModel):
    operator: str
    target: str
    rows: list[NumericRow] = Field(default_factory=list)
    source_chunk_ids: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
