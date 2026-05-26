from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone

from .models import Turn


TIMESTAMPED_TURN_RE = re.compile(
    r"^\[?(?P<ts>\d{1,2}:\d{2}(?::\d{2})?)\]?\s+(?P<speaker>[^:：]{1,40})[:：]\s*(?P<content>.+)$"
)
SPEAKER_TURN_RE = re.compile(r"^(?P<speaker>[^:：\[\]#・•]{1,30})[:：]\s*(?P<content>.+)$")
DOC_FIELD_LABELS = {
    "会社名",
    "英語名",
    "法人種別",
    "税務番号",
    "本社所在地",
    "執行責任者 (CEO)",
    "代表取締役",
    "設立",
    "DX-ASAP",
    "Energy Japan",
    "GoEMON Jobs",
    "GoEMON Home",
    "GoEMON Community",
    "VJ Technologies",
    "ONE Financial Service",
}


def _parse_time(ts: str, reference_date: date | None) -> datetime:
    pieces = [int(p) for p in ts.split(":")]
    if len(pieces) == 2:
        pieces.append(0)
    base_date = reference_date or date.today()
    return datetime.combine(base_date, time(pieces[0], pieces[1], pieces[2]), tzinfo=timezone.utc)


def _clean_markdown_line(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^[*\-]+ ", "", line)
    line = re.sub(r"^[・•]\s*", "", line)
    line = re.sub(r"^\d+[.)]\s*", "", line)
    return line.strip()


def split_turns(raw_transcript: str, reference_date: date | None = None) -> list[Turn]:
    """Split transcript-like text and markdown sample documents into turns."""
    turns: list[Turn] = []
    for raw_line in raw_transcript.splitlines():
        line = _clean_markdown_line(raw_line)
        if not line or line == "---":
            continue
        line = line.strip("# ")
        if not line:
            continue

        ts_match = TIMESTAMPED_TURN_RE.match(line)
        if ts_match:
            turns.append(
                Turn(
                    turn_index=len(turns),
                    speaker=ts_match.group("speaker").strip(),
                    content=ts_match.group("content").strip(),
                    timestamp=_parse_time(ts_match.group("ts"), reference_date),
                )
            )
            continue

        speaker_match = SPEAKER_TURN_RE.match(line)
        if speaker_match and speaker_match.group("speaker").strip() not in DOC_FIELD_LABELS:
            turns.append(
                Turn(
                    turn_index=len(turns),
                    speaker=speaker_match.group("speaker").strip(),
                    content=speaker_match.group("content").strip(),
                    timestamp=None,
                )
            )
            continue

        turns.append(Turn(turn_index=len(turns), speaker="document", content=line, timestamp=None))
    return turns


def chunk_turns_into_passages(
    turns: list[Turn],
    max_turns: int = 10,
    min_turns: int = 8,
    silence_threshold_seconds: int = 180,
) -> list[list[Turn]]:
    if max_turns <= 0:
        raise ValueError("max_turns must be positive")
    if min_turns <= 0 or min_turns > max_turns:
        raise ValueError("min_turns must be between 1 and max_turns")

    passages: list[list[Turn]] = []
    current: list[Turn] = []
    previous_ts: datetime | None = None
    threshold = timedelta(seconds=silence_threshold_seconds)

    for turn in turns:
        should_split_for_silence = (
            current
            and previous_ts is not None
            and turn.timestamp is not None
            and turn.timestamp - previous_ts > threshold
        )
        should_split_for_size = len(current) >= max_turns

        if should_split_for_silence or should_split_for_size:
            passages.append(current)
            current = []

        current.append(turn)
        previous_ts = turn.timestamp or previous_ts

    if current:
        passages.append(current)

    if len(passages) >= 2 and len(passages[-1]) < min_turns:
        tail = passages.pop()
        passages[-1].extend(tail)

    return passages


def passage_content(turns: list[Turn]) -> str:
    return "\n".join(f"{turn.speaker}: {turn.content}" for turn in turns)
