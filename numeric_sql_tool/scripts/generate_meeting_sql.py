"""Generate transcripts / chunks SQL from data-test/timestamp transcript files.

Reads from data-test/timestamp/GT_*.txt which use the format:
    [HH:MM:SS-HH:MM:SS][Speaker] text content
Produces accurate timestamps and durations instead of the old fake 10s-per-line approach.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
import glob
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Now reads from the timestamp sub-folder which has real timing data
DATA_TEST_DIR = ROOT / "data-test" / "timestamp"
OUT_DIR = ROOT / "db" / "data"

USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")
PROJECT_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "javis-chatbot-test")

# Matches: [HH:MM:SS-HH:MM:SS][Speaker] text
TIMESTAMPED_TURN_RE = re.compile(
    r"^\[(\d{1,2}:\d{2}:\d{2})-(\d{1,2}:\d{2}:\d{2})\]\[([^\]]+)\]\s*(.+)$"
)

def _uuid(name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"javis-chatbot/{name}")

def _sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"

def _sql_json(value: object) -> str:
    return _sql_str(json.dumps(value, ensure_ascii=False))

def _ts_to_sec(ts: str) -> int:
    """Convert HH:MM:SS to total seconds (integer)."""
    parts = ts.split(":")
    h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
    return h * 3600 + m * 60 + s

def _parse_file(filepath: Path) -> list[dict[str, object]]:
    """Parse a timestamped transcript file into a list of turn dicts."""
    lines = filepath.read_text(encoding="utf-8").splitlines()
    turns: list[dict[str, object]] = []
    alternating_speaker = "A"

    for line in lines:
        line = line.strip()
        if not line:
            continue

        m = TIMESTAMPED_TURN_RE.match(line)
        if m:
            ts_start, ts_end, speaker, text = m.group(1), m.group(2), m.group(3).strip(), m.group(4).strip()
            start_sec = _ts_to_sec(ts_start)
            end_sec = _ts_to_sec(ts_end)
            # Guard against typo inversions (end < start) — clamp to start+1
            if end_sec < start_sec:
                end_sec = start_sec + 1
        else:
            # Fallback for plain lines without timestamps — assign synthetic timing
            start_sec = len(turns) * 10
            end_sec = start_sec + 10
            # Try to detect speaker from "Speaker: text" pattern
            plain_m = re.match(r"^([A-Za-z0-9Nữam１２\s]+)[:：]\s*(.+)$", line)
            if plain_m and plain_m.group(1).strip() not in ("", "---"):
                speaker = plain_m.group(1).strip()
                text = plain_m.group(2).strip()
            else:
                speaker = alternating_speaker
                text = line
                alternating_speaker = "B" if alternating_speaker == "A" else "A"

        turns.append({
            "speaker": speaker,
            "time_start_sec": start_sec,
            "time_end_sec": end_sec,
            "text": text,
        })
    return turns


def _build_meeting(filepath: Path, index: int) -> dict[str, object]:
    session_id = filepath.stem  # e.g. GT_01
    # Auto-generate dates in May 2026: May 01, May 02, etc.
    meeting_date = f"2026-05-{index:02d}"

    turns = _parse_file(filepath)
    if not turns:
        raise RuntimeError(f"No turns in file {filepath.name}")

    transcript_id = _uuid(f"transcript/{session_id}")
    all_speakers = sorted(list(set(str(t["speaker"]) for t in turns)))

    raw_parts = [f"[{t['speaker']}]:{t['text']}" for t in turns]
    raw_text = "".join(raw_parts)

    # Derive real duration from the maximum turn end time
    duration_seconds = max(int(t["time_end_sec"]) for t in turns)

    content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    created = f"{meeting_date} 10:00:00+07"

    # We place the entire transcript into a single passage
    passage_id = _uuid(f"passage/{session_id}/0")
    passage_lines = [f"[{t['speaker']}] {t['text']}" for t in turns]
    passages = [
        {
            "id": passage_id,
            "transcript_id": transcript_id,
            "passage_index": 0,
            "time_start_sec": int(turns[0]["time_start_sec"]),
            "time_end_sec": duration_seconds,
            "speaker_list": all_speakers,
            "text": "\n".join(passage_lines),
            "chunk_metadata": {
                "topics": ["general"],
                "entities": all_speakers,
                "turn_types": ["update"],
                "importance_score": 4,
            },
            "importance_score": 4,
            "created_at": created,
        }
    ]

    turn_rows = []
    for global_idx, t in enumerate(turns):
        turn_rows.append(
            {
                "id": _uuid(f"turn/{session_id}/{global_idx}"),
                "transcript_id": transcript_id,
                "passage_id": passage_id,
                "turn_index": global_idx,
                "speaker": t["speaker"],
                "time_start_sec": int(t["time_start_sec"]),
                "time_end_sec": int(t["time_end_sec"]),
                "text": t["text"],
                "sub_chunk_index": 0,
                "chunk_metadata": {
                    "topics": ["general"],
                    "entities": [t["speaker"]],
                    "turn_types": ["update"],
                    "importance_score": 3,
                },
                "importance_score": 3,
                "created_at": created,
            }
        )

    summary = f"Transcript of meeting {session_id}."
    return {
        "transcript": {
            "id": transcript_id,
            "session_id": session_id,
            "user_id": USER_ID,
            "meeting_date": meeting_date,
            "participants": all_speakers,
            "speaker_count": len(all_speakers),
            "duration_seconds": duration_seconds,
            "content_hash": content_hash,
            "raw_text": raw_text,
            "summary": summary,
            "summary_metadata": {
                "topics": ["general"],
                "entities": all_speakers,
            },
            "status": "ready",
            "qdrant_synced": True,
            "ingest_tokens_in": 0,
            "ingest_tokens_out": 0,
            "created_at": created,
            "updated_at": created,
            "project_id": PROJECT_ID,
        },
        "passages": passages,
        "turns": turn_rows,
    }

def _emit_transcripts(meetings: list[dict[str, object]]) -> str:
    cols = (
        "id,session_id,user_id,meeting_date,participants,speaker_count,duration_seconds,"
        "content_hash,raw_text,summary,summary_metadata,status,error,qdrant_synced,"
        "ingest_tokens_in,ingest_tokens_out,created_at,updated_at,project_id"
    )
    lines = [f"INSERT INTO public.transcripts ({cols}) VALUES"]
    values = []
    for m in meetings:
        t = m["transcript"]
        values.append(
            "\t("
            f"{_sql_str(str(t['id']))}::uuid,"
            f"{_sql_str(t['session_id'])},"
            f"{_sql_str(str(t['user_id']))}::uuid,"
            f"{_sql_str(t['meeting_date'])},"
            f"{_sql_json(t['participants'])},"
            f"{t['speaker_count']},"
            f"{t['duration_seconds']},"
            f"{_sql_str(t['content_hash'])},"
            f"{_sql_str(t['raw_text'])},"
            f"{_sql_str(t['summary'])},"
            f"{_sql_json(t['summary_metadata'])},"
            f"{_sql_str(t['status'])},"
            "NULL,"
            f"{str(t['qdrant_synced']).lower()},"
            f"{t['ingest_tokens_in']},"
            f"{t['ingest_tokens_out']},"
            f"{_sql_str(t['created_at'])},"
            f"{_sql_str(t['updated_at'])},"
            f"{_sql_str(str(t['project_id']))}::uuid)"
        )
    lines.append(",\n".join(values) + ";")
    return "\n".join(lines) + "\n"

def _emit_passages(meetings: list[dict[str, object]]) -> str:
    cols = (
        "id,transcript_id,passage_index,time_start_sec,time_end_sec,speaker_list,text,"
        "chunk_metadata,importance_score,enrich_error,qdrant_synced,created_at"
    )
    lines = [f"INSERT INTO public.chunks_passage ({cols}) VALUES"]
    values = []
    for m in meetings:
        for p in m["passages"]:
            values.append(
                "\t("
                f"{_sql_str(str(p['id']))}::uuid,"
                f"{_sql_str(str(p['transcript_id']))}::uuid,"
                f"{p['passage_index']},"
                f"{p['time_start_sec']},"
                f"{p['time_end_sec']},"
                f"{_sql_json(p['speaker_list'])},"
                f"{_sql_str(p['text'])},"
                f"{_sql_json(p['chunk_metadata'])},"
                f"{p['importance_score']},"
                "NULL,"
                "true,"
                f"{_sql_str(p['created_at'])})"
            )
    lines.append(",\n".join(values) + ";")
    return "\n".join(lines) + "\n"

def _emit_turns(meetings: list[dict[str, object]]) -> str:
    cols = (
        "id,transcript_id,passage_id,turn_index,speaker,time_start_sec,time_end_sec,text,"
        "sub_chunk_index,chunk_metadata,importance_score,enrich_error,qdrant_synced,created_at"
    )
    lines = [f"INSERT INTO public.chunks_turn ({cols}) VALUES"]
    values = []
    for m in meetings:
        for t in m["turns"]:
            values.append(
                "\t("
                f"{_sql_str(str(t['id']))}::uuid,"
                f"{_sql_str(str(t['transcript_id']))}::uuid,"
                f"{_sql_str(str(t['passage_id']))}::uuid,"
                f"{t['turn_index']},"
                f"{_sql_str(t['speaker'])},"
                f"{t['time_start_sec']},"
                f"{t['time_end_sec']},"
                f"{_sql_str(t['text'])},"
                f"{t['sub_chunk_index']},"
                f"{_sql_json(t['chunk_metadata'])},"
                f"{t['importance_score']},"
                "NULL,"
                "true,"
                f"{_sql_str(t['created_at'])})"
            )
    lines.append(",\n".join(values) + ";")
    return "\n".join(lines) + "\n"

def main() -> None:
    import sys
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    txt_files = sorted(list(DATA_TEST_DIR.glob("GT_*.txt")))
    if not txt_files:
        raise RuntimeError(f"No GT_*.txt files found in {DATA_TEST_DIR}")

    meetings = []
    for idx, filepath in enumerate(txt_files, start=1):
        meetings.append(_build_meeting(filepath, idx))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "transcripts.sql").write_text(_emit_transcripts(meetings), encoding="utf-8")
    (OUT_DIR / "chunks_passage.sql").write_text(_emit_passages(meetings), encoding="utf-8")
    (OUT_DIR / "chunks_turn.sql").write_text(_emit_turns(meetings), encoding="utf-8")

    print(f"Wrote SQL files for {len(meetings)} meetings from {DATA_TEST_DIR} to {OUT_DIR}")
    for m in meetings:
        t = m["transcript"]
        print(f"  {t['session_id']}: date={t['meeting_date']}, duration={t['duration_seconds']}s, {len(m['turns'])} turns, speakers={t['participants']}")

if __name__ == "__main__":
    main()
