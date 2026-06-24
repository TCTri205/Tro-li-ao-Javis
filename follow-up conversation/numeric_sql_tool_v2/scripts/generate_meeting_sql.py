"""Generate simplified INSERT SQL from data_docs (debug only).

Production data: use leader dump + `numeric-sql-tool restore-db` or `python scripts/restore_db.py`.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DOCS = ROOT / "data_docs"
OUT_DIR = ROOT / "db" / "data"

USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
PROJECT_ID = uuid.UUID("00000000-0000-0000-0000-000000000101")

# Maps data_docs/scriptN → leader session_id + meeting_date (May 2026).
SCRIPTS: tuple[tuple[str, str, str, str], ...] = (
    (
        "script1",
        "ingest-media-gt_01-2026-05-01",
        "2026-05-01",
        "梅田様への返信・サイズ書配送、スリーラスター様（購入・サイズ書なし）の電話確認。",
    ),
    (
        "script2",
        "ingest-media-gt_02-2026-05-02",
        "2026-05-02",
        "アセットジャパン受付。バルテス中岡よりPMG石田（志保）様への電話（在宅・折り返し予定）。",
    ),
    (
        "script3",
        "ingest-media-gt_03-2026-05-03",
        "2026-05-03",
        "アセットジャパン受付。島田様より物件前での内見・売却状況確認の折り返し依頼。",
    ),
    (
        "script4",
        "ingest-media-gt_04-2026-05-04",
        "2026-05-04",
        "三菱UFJ銀行横堀より、勤務中のアルバイト中原凛花様への伝言依頼（本日休み）。",
    ),
    (
        "script5",
        "ingest-media-gt_05-2026-05-05",
        "2026-05-05",
        "株式会社サカモトとアセットジャパン。来週14日（水）10時の打ち合わせ日程調整。",
    ),
    (
        "script6",
        "ingest-media-gt_06-2026-05-06",
        "2026-05-06",
        "建設のエスタ受付。AJテクノロジーズ山下よりカセ様不在のため改めて連絡。",
    ),
    (
        "script7",
        "ingest-media-gt_07-2026-05-07",
        "2026-05-07",
        "アセットジャパン熊谷と先方。14日水曜10時の訪問打ち合わせ再確認。",
    ),
    (
        "script8",
        "ingest-media-gt_08-2026-05-08",
        "2026-05-08",
        "保険代理店ベネフィットへのアウトバウンド。AJテクノロジーズ辻より代表野田様不在。",
    ),
    (
        "script9",
        "ingest-media-gt_09-2026-05-09",
        "2026-05-09",
        "中央清算管理課。アセットジャパン伊藤より山内様宛・東浦町物件のメール問い合わせ伝言。",
    ),
)

LINE_RE = re.compile(
    r"^\[(?P<start>\d{2}:\d{2}:\d{2}(?:\.\d+)?)-(?P<end>\d{2}:\d{2}:\d{2}(?:\.\d+)?)\]"
    r"\[(?P<speaker>[^\]]+)\]\s*(?P<text>.*)$",
    re.DOTALL,
)


def _uuid(name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"javis-chatbot/{name}")


def _ts_to_sec(ts: str) -> int:
    h, m, s_part = ts.split(":")
    s = float(s_part)
    return int(h) * 3600 + int(m) * 60 + int(s)


def _sql_str(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _sql_json(value: object) -> str:
    return _sql_str(json.dumps(value, ensure_ascii=False))


def _parse_turn(line: str) -> dict[str, object]:
    m = LINE_RE.match(line.strip())
    if not m:
        raise ValueError(f"Unrecognized turn format: {line[:80]!r}")
    return {
        "speaker": m.group("speaker").strip(),
        "time_start_sec": _ts_to_sec(m.group("start")),
        "time_end_sec": _ts_to_sec(m.group("end")),
        "text": m.group("text"),
    }


def _load_script(script_folder: str) -> list[dict[str, object]]:
    path = DATA_DOCS / script_folder / "ja.txt"
    if not path.is_file():
        raise FileNotFoundError(path)
    turns: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        turns.append(_parse_turn(line))
    return turns


def _unique_speakers(turns: list[dict[str, object]]) -> list[str]:
    speakers: list[str] = []
    seen: set[str] = set()
    for t in turns:
        sp = str(t["speaker"])
        if sp not in seen:
            seen.add(sp)
            speakers.append(sp)
    return speakers


def _build_script(
    script_folder: str, db_session_id: str, meeting_date: str, summary: str
) -> dict[str, object]:
    turns = _load_script(script_folder)
    if not turns:
        raise RuntimeError(f"No turns in {script_folder}")

    transcript_id = _uuid(f"transcript/{db_session_id}")
    session_id = db_session_id
    all_speakers = _unique_speakers(turns)

    raw_parts = [f"[{t['speaker']}]:{t['text']}" for t in turns]
    raw_text = "".join(raw_parts)
    duration_seconds = max(0, int(turns[-1]["time_end_sec"]) - int(turns[0]["time_start_sec"]))
    content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    created = f"{meeting_date} 10:00:00+07"

    passage_id = _uuid(f"passage/{db_session_id}/0")
    passage_lines = [f"[{t['speaker']}] {t['text']}" for t in turns]
    passage = {
        "id": passage_id,
        "transcript_id": transcript_id,
        "passage_index": 0,
        "time_start_sec": int(turns[0]["time_start_sec"]),
        "time_end_sec": int(turns[-1]["time_end_sec"]),
        "speaker_list": all_speakers,
        "text": "\n".join(passage_lines),
        "chunk_metadata": {
            "topics": ["call"],
            "entities": all_speakers,
            "turn_types": ["update"],
            "importance_score": 4,
        },
        "importance_score": 4,
        "created_at": created,
    }

    turn_rows: list[dict[str, object]] = []
    for idx, t in enumerate(turns):
        turn_rows.append(
            {
                    "id": _uuid(f"turn/{db_session_id}/{idx}"),
                "transcript_id": transcript_id,
                "passage_id": passage_id,
                "turn_index": idx,
                "speaker": t["speaker"],
                "time_start_sec": t["time_start_sec"],
                "time_end_sec": t["time_end_sec"],
                "text": t["text"],
                "sub_chunk_index": 0,
                "chunk_metadata": {
                    "topics": ["call"],
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
            "summary": summary,
            "summary_metadata": {
                "topics": ["call"],
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
        "passages": [passage],
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
    meetings = [
        _build_script(folder, session_id, meeting_date, summary)
        for folder, session_id, meeting_date, summary in SCRIPTS
    ]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "transcripts.sql").write_text(_emit_transcripts(meetings), encoding="utf-8")
    (OUT_DIR / "chunks_passage.sql").write_text(_emit_passages(meetings), encoding="utf-8")
    (OUT_DIR / "chunks_turn.sql").write_text(_emit_turns(meetings), encoding="utf-8")

    total_turns = sum(len(m["turns"]) for m in meetings)
    print("Wrote SQL files to", OUT_DIR)
    print(f"  {len(meetings)} transcripts, {total_turns} turns total")
    for m in meetings:
        t = m["transcript"]
        print(
            f"  {t['session_id']} ({t['meeting_date']}): "
            f"{len(m['turns'])} turns, duration={t['duration_seconds']}s"
        )


if __name__ == "__main__":
    main()
