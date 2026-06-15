from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class NumericIntent(BaseModel):
    operator: Literal["sum", "avg", "max", "min", "count", "skip", "none"] = "none"
    target: Literal[
        "duration_seconds",   # meeting-level duration (seconds) from transcripts table
        "meeting_count",      # number of meetings from transcripts table
        "turn_count",         # number of turns (utterances) from chunks_turn table
        "turn_duration",      # per-turn duration (time_end_sec - time_start_sec) from chunks_turn
        "mention_count",      # count of text mentions of an entity in chunks_turn.text
        "speaker_name",       # return speaker name (for argmax/argmin queries)
        "time_start_sec",     # turn-level timestamp (always skip)
        "none",
    ] = "none"
    group_by: Literal["none", "user_id", "day", "speaker"] = "none"
    context_filter: str | None = None
    speaker_filter: str | None = None  # e.g. "SPEAKER 1" — filter chunks_turn by speaker
    entity_filter: str | None = None   # e.g. "梅田" — entity to count mentions of


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
