from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from javis_text2sql.etl.chunker import chunk_turns_into_passages, split_turns
from javis_text2sql.etl.models import PassageEnrichmentSchema, Turn


def test_split_turns_supports_timestamped_transcript_and_markdown_fallback() -> None:
    raw = """
[10:00:00] Bình: Chúng ta cần chốt ngân sách.
[10:01:00] Lan: Tôi sẽ gửi báo cáo.
•総予算（土地・建物・諸費用）上限：約４,５００万円。
"""
    turns = split_turns(raw, reference_date=date(2026, 5, 26))
    assert [(turn.speaker, turn.content) for turn in turns[:2]] == [
        ("Bình", "Chúng ta cần chốt ngân sách."),
        ("Lan", "Tôi sẽ gửi báo cáo."),
    ]
    assert turns[2].speaker == "document"
    assert "４,５００万円" in turns[2].content


def test_chunker_limits_size_and_splits_on_silence() -> None:
    raw = """
[10:00:00] A: one
[10:01:00] B: two
[10:05:30] A: three
"""
    turns = split_turns(raw, reference_date=date(2026, 5, 26))
    chunks = chunk_turns_into_passages(turns, max_turns=10, min_turns=1, silence_threshold_seconds=180)
    assert [len(chunk) for chunk in chunks] == [2, 1]

    sized = [Turn(i, "s", f"turn {i}") for i in range(21)]
    size_chunks = chunk_turns_into_passages(sized, max_turns=10)
    assert [len(chunk) for chunk in size_chunks] == [10, 11]


def test_pydantic_schema_enforces_consistency_and_ranges() -> None:
    with pytest.raises(ValidationError):
        PassageEnrichmentSchema(has_action_item=True, action_item_text=None)
    with pytest.raises(ValidationError):
        PassageEnrichmentSchema(has_question=True, question_text=None)
    with pytest.raises(ValidationError):
        PassageEnrichmentSchema(importance_score=6)
    with pytest.raises(ValidationError):
        PassageEnrichmentSchema(sentiment="angry")  # type: ignore[arg-type]

    valid = PassageEnrichmentSchema(
        has_action_item=True,
        action_item_text="Prepare financing plan",
        commitments=[{"person": "A", "action": "Prepare financing plan", "status": "pending"}],
        importance_score=5,
    )
    assert valid.commitments[0].commitment_id
