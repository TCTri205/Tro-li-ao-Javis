"""Generate transcripts / chunks SQL from Test javis chatbot.xlsx meeting sheets."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
XLSX = ROOT / "db" / "Test javis chatbot.xlsx"
OUT_DIR = ROOT / "db" / "data"

USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")
PROJECT_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "javis-chatbot-test")

MEETINGS = (
    ("meeting_01_20260526", "2026-05-26"),
    ("meeting_02_20260520", "2026-05-20"),
    ("meeting_03_20260515", "2026-05-15"),
)

SUMMARIES = {
    "meeting_01_20260526": (
        "定例会議。音声認識システムバージョン2.3の開発進捗とノイズキャンセリング問題、"
        "第二四半期予算（一億五千万円）の執行状況とクラウドコスト超過、"
        "新エネルギー政策への対応（計測システム・太陽光パネル・省エネ研修）を議論。"
    ),
    "meeting_02_20260520": (
        "第一四半期営業レビュー。Q1売上四億二千万円（達成率百八パーセント）、"
        "Q2マーケティング予算五千万円、下半期採用計画（七名・三千五百万円）を審議。"
    ),
    "meeting_03_20260515": (
        "新製品「AiVoice Pro」ローンチ計画会議。技術仕様・価格戦略・"
        "九月一日正式ローンチ、初年度売上目標十二億円、ベータプログラムとリスク分析を議論。"
    ),
}

# (topic label, substring markers) — new passage starts at first turn containing any marker.
# First segment always starts at turn 0.
# Transition phrases only (avoid agenda mentions in the opening turn).
PASSAGE_SEGMENTS: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "meeting_01_20260526": [
        ("opening", ()),
        ("project_progress", ("プロジェクト進捗に移りましょう",)),
        ("budget_q2", ("予算の話に移りましょう",)),
        ("energy_policy", ("エネルギー政策への対応についてです",)),
        ("action_items", ("アクションアイテムを確認しましょう",)),
    ],
    "meeting_02_20260520": [
        ("opening", ()),
        ("q1_sales", ("まず全体的な数字を共有",)),
        ("q2_marketing", ("Q2のマーケティング戦略を説明してください",)),
        ("hiring_plan", ("採用計画に移りましょう",)),
        ("action_items", ("アクションアイテムを確認しましょう",)),
    ],
    "meeting_03_20260515": [
        ("opening", ()),
        ("product_overview", ("ポジショニングから確認しましょう",)),
        ("technical_specs", ("技術仕様について詳しく説明してください",)),
        ("pricing", ("価格戦略を説明してください",)),
        ("go_to_market", ("市場投入計画に移りましょう",)),
        ("risk_analysis", ("リスク分析をお願いします",)),
        ("action_items", ("アクションアイテムをまとめましょう",)),
    ],
}

LINE_RE = re.compile(
    r"^\[(?P<start>\d{2}:\d{2}:\d{2})-(?P<end>\d{2}:\d{2}:\d{2})\]\[(?P<speaker>[^\]]+)\]\s*(?P<text>.*)$",
    re.DOTALL,
)


def _uuid(name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"javis-chatbot/{name}")


def _ts_to_sec(ts: str) -> int:
    h, m, s = (int(x) for x in ts.split(":"))
    return h * 3600 + m * 60 + s


def _sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _sql_json(value: object) -> str:
    return _sql_str(json.dumps(value, ensure_ascii=False))


def _parse_turn(ja_cell: str) -> dict[str, object]:
    m = LINE_RE.match(ja_cell.strip())
    if not m:
        raise ValueError(f"Unrecognized turn format: {ja_cell[:80]!r}")
    return {
        "speaker": m.group("speaker"),
        "time_start_sec": _ts_to_sec(m.group("start")),
        "time_end_sec": _ts_to_sec(m.group("end")),
        "text": m.group("text"),
    }


def _load_meeting(sheet: str) -> list[dict[str, object]]:
    df = pd.read_excel(XLSX, sheet_name=sheet, header=None)
    turns: list[dict[str, object]] = []
    for row in df.itertuples(index=False):
        ja = row[0]
        if pd.isna(ja):
            continue
        turns.append(_parse_turn(str(ja)))
    return turns


def _passage_boundaries(sheet: str, turns: list[dict[str, object]]) -> list[int]:
    """Return start turn indices for each passage segment."""
    segments = PASSAGE_SEGMENTS[sheet]
    boundaries = [0]
    for _topic, markers in segments[1:]:
        start_at = boundaries[-1] + 1
        found = None
        for i in range(start_at, len(turns)):
            text = str(turns[i]["text"])
            if any(marker in text for marker in markers):
                found = i
                break
        if found is None:
            raise RuntimeError(
                f"{sheet}: passage marker not found: {markers!r} (after turn {start_at - 1})"
            )
        boundaries.append(found)
    return boundaries


def _group_passages(
    sheet: str, turns: list[dict[str, object]]
) -> list[dict[str, object]]:
    segments = PASSAGE_SEGMENTS[sheet]
    boundaries = _passage_boundaries(sheet, turns)
    groups: list[dict[str, object]] = []
    for seg_idx, start in enumerate(boundaries):
        end = boundaries[seg_idx + 1] if seg_idx + 1 < len(boundaries) else len(turns)
        topic = segments[seg_idx][0]
        seg_turns = turns[start:end]
        groups.append({"topic": topic, "turns": seg_turns, "start_index": start})
    return groups


def _unique_speakers(turns: list[dict[str, object]]) -> list[str]:
    speakers: list[str] = []
    seen: set[str] = set()
    for t in turns:
        sp = str(t["speaker"])
        if sp not in seen:
            seen.add(sp)
            speakers.append(sp)
    return speakers


def _build_meeting(sheet: str, meeting_date: str) -> dict[str, object]:
    turns = _load_meeting(sheet)
    if not turns:
        raise RuntimeError(f"No turns in sheet {sheet}")

    transcript_id = _uuid(f"transcript/{sheet}")
    session_id = sheet
    all_speakers = _unique_speakers(turns)

    raw_parts = [f"[{t['speaker']}]:{t['text']}" for t in turns]
    raw_text = "".join(raw_parts)
    duration_seconds = int(turns[-1]["time_end_sec"]) - int(turns[0]["time_start_sec"])
    content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    created = f"{meeting_date} 10:00:00+07"

    passage_groups = _group_passages(sheet, turns)
    passages: list[dict[str, object]] = []
    turn_rows: list[dict[str, object]] = []

    for passage_index, group in enumerate(passage_groups):
        seg_turns: list[dict[str, object]] = group["turns"]
        topic = str(group["topic"])
        passage_id = _uuid(f"passage/{sheet}/{passage_index}")
        seg_speakers = _unique_speakers(seg_turns)
        passage_lines = [f"[{t['speaker']}] {t['text']}" for t in seg_turns]

        passages.append(
            {
                "id": passage_id,
                "transcript_id": transcript_id,
                "passage_index": passage_index,
                "time_start_sec": int(seg_turns[0]["time_start_sec"]),
                "time_end_sec": int(seg_turns[-1]["time_end_sec"]),
                "speaker_list": seg_speakers,
                "text": "\n".join(passage_lines),
                "chunk_metadata": {
                    "topics": [topic],
                    "entities": seg_speakers,
                    "turn_types": ["update"],
                    "importance_score": 4,
                },
                "importance_score": 4,
                "created_at": created,
            }
        )

        for local_idx, t in enumerate(seg_turns):
            global_idx = int(group["start_index"]) + local_idx
            turn_rows.append(
                {
                    "id": _uuid(f"turn/{sheet}/{global_idx}"),
                    "transcript_id": transcript_id,
                    "passage_id": passage_id,
                    "turn_index": global_idx,
                    "speaker": t["speaker"],
                    "time_start_sec": t["time_start_sec"],
                    "time_end_sec": t["time_end_sec"],
                    "text": t["text"],
                    "sub_chunk_index": 0,
                    "chunk_metadata": {
                        "topics": [topic],
                        "entities": [t["speaker"]],
                        "turn_types": ["update"],
                        "importance_score": 3,
                    },
                    "importance_score": 3,
                    "created_at": created,
                }
            )

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
            "summary": SUMMARIES[sheet],
            "summary_metadata": {
                "topics": [seg[0] for seg in PASSAGE_SEGMENTS[sheet]],
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
    meetings = [_build_meeting(sheet, date) for sheet, date in MEETINGS]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "transcripts.sql").write_text(_emit_transcripts(meetings), encoding="utf-8")
    (OUT_DIR / "chunks_passage.sql").write_text(_emit_passages(meetings), encoding="utf-8")
    (OUT_DIR / "chunks_turn.sql").write_text(_emit_turns(meetings), encoding="utf-8")

    print("Wrote SQL files to", OUT_DIR)
    for sheet, _date in MEETINGS:
        m = next(x for x in meetings if x["transcript"]["session_id"] == sheet)
        passage_topics = [
            f"p{p['passage_index']}:{p['chunk_metadata']['topics'][0]}"
            for p in m["passages"]
        ]
        print(
            f"  {sheet}: {len(m['turns'])} turns, {len(m['passages'])} passages "
            f"({', '.join(passage_topics)}), duration={m['transcript']['duration_seconds']}s"
        )


if __name__ == "__main__":
    main()
