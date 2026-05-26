from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from javis_text2sql.config import SAMPLE_DATA_DIR
from javis_text2sql.etl.chunker import split_turns
from javis_text2sql.etl.loader import load_meeting
from javis_text2sql.etl.models import MeetingMeta
from javis_text2sql.llm.client import LLMClient


SAMPLE_META: dict[str, MeetingMeta] = {
    "VJ_technologies_ja.md": MeetingMeta(
        title="VJ Technologies company profile",
        meeting_date=date(2026, 5, 26),
        speaker_count=1,
        duration_seconds=0,
        summary="VJ Technologies company and product profile.",
        source_language="ja",
    ),
    "AJ_technologies_ja.md": MeetingMeta(
        title="AJ Technologies company profile",
        meeting_date=date(2026, 5, 26),
        speaker_count=1,
        duration_seconds=0,
        summary="AJ Technologies company, partners, and platform profile.",
        source_language="ja",
    ),
    "sumary_mau.md": MeetingMeta(
        title="Housing negotiation sample summary",
        meeting_date=date(2026, 5, 26),
        speaker_count=2,
        duration_seconds=5400,
        summary="Sample commercial negotiation summary with budget, dates, and commitments.",
        source_language="ja",
    ),
}


def list_sample_files(sample_dir: Path = SAMPLE_DATA_DIR) -> list[Path]:
    return [sample_dir / name for name in SAMPLE_META if (sample_dir / name).exists()]


def read_sample(path: Path) -> str:
    return path.read_text(encoding="utf-8")


async def ingest_sample_files(
    db_pool: Any,
    llm_client: LLMClient,
    sample_dir: Path = SAMPLE_DATA_DIR,
) -> list[str]:
    meeting_ids: list[str] = []
    for path in list_sample_files(sample_dir):
        raw = read_sample(path)
        meta = SAMPLE_META[path.name]
        turns = split_turns(raw, reference_date=meta.meeting_date)
        meeting_id = await load_meeting(raw, meta, db_pool, llm_client, turns=turns)
        meeting_ids.append(meeting_id)
    return meeting_ids
