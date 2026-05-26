from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
import tiktoken

from .models import Turn

try:
    _encoding = tiktoken.get_encoding("cl100k_base")
except Exception:
    _encoding = None


def count_tokens(text: str) -> int:
    if _encoding is not None:
        return len(_encoding.encode(text))
    return len(text) // 4


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"([.!?。？！\n])", text)
    sentences = []
    current = ""
    for part in parts:
        if not part:
            continue
        current += part
        if part in {".", "!", "?", "。", "？", "！", "\n"}:
            if current.strip():
                sentences.append(current.strip())
            current = ""
    if current.strip():
        sentences.append(current.strip())
    return sentences


def split_huge_sentence(sentence: str, max_tokens: int = 400) -> list[str]:
    parts = []
    current_chars = []
    for char in sentence:
        current_chars.append(char)
        if count_tokens("".join(current_chars)) >= max_tokens - 10:
            parts.append("".join(current_chars))
            current_chars = []
    if current_chars:
        parts.append("".join(current_chars))
    return parts


def chunk_sentences(sentences: list[str], max_tokens: int = 400, overlap_count: int = 1) -> list[str]:
    if not sentences:
        return []
    
    chunks = []
    i = 0
    sentences_list = list(sentences)
    num_sentences = len(sentences_list)
    
    while i < num_sentences:
        current_sentences = []
        current_tokens = 0
        j = i
        
        while j < num_sentences:
            sentence = sentences_list[j]
            sentence_tokens = count_tokens(sentence)
            
            if current_tokens + sentence_tokens > max_tokens:
                if not current_sentences:
                    if sentence_tokens > max_tokens:
                        sub_parts = split_huge_sentence(sentence, max_tokens)
                        sentences_list[j:j+1] = sub_parts
                        num_sentences = len(sentences_list)
                        continue
                    else:
                        current_sentences.append(sentence)
                        current_tokens += sentence_tokens
                        j += 1
                        break
                else:
                    break
            else:
                current_sentences.append(sentence)
                current_tokens += sentence_tokens
                j += 1
        
        chunks.append(" ".join(current_sentences))
        if j == num_sentences:
            break
        next_i = max(i + 1, j - overlap_count)
        i = next_i
        
    return chunks


def sub_chunk_text(text: str, max_tokens: int = 400, overlap_count: int = 1) -> list[str]:
    if count_tokens(text) <= max_tokens:
        return [text]
    
    sentences = split_sentences(text)
    if not sentences:
        return [text]
        
    return chunk_sentences(sentences, max_tokens=max_tokens, overlap_count=overlap_count)


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


def split_turns(
    raw_transcript: str,
    reference_date: date | None = None,
    max_tokens: int = 400,
    overlap_count: int = 1,
) -> list[Turn]:
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
            speaker = ts_match.group("speaker").strip()
            content = ts_match.group("content").strip()
            timestamp = _parse_time(ts_match.group("ts"), reference_date)
            for sub_content in sub_chunk_text(content, max_tokens=max_tokens, overlap_count=overlap_count):
                turns.append(
                    Turn(
                        turn_index=len(turns),
                        speaker=speaker,
                        content=sub_content,
                        timestamp=timestamp,
                    )
                )
            continue

        speaker_match = SPEAKER_TURN_RE.match(line)
        if speaker_match and speaker_match.group("speaker").strip() not in DOC_FIELD_LABELS:
            speaker = speaker_match.group("speaker").strip()
            content = speaker_match.group("content").strip()
            for sub_content in sub_chunk_text(content, max_tokens=max_tokens, overlap_count=overlap_count):
                turns.append(
                    Turn(
                        turn_index=len(turns),
                        speaker=speaker,
                        content=sub_content,
                        timestamp=None,
                    )
                )
            continue

        for sub_content in sub_chunk_text(line, max_tokens=max_tokens, overlap_count=overlap_count):
            turns.append(Turn(turn_index=len(turns), speaker="document", content=sub_content, timestamp=None))
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
