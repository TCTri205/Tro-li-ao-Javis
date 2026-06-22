import asyncio
import asyncpg
import os
import re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("NUMERIC_SQL_DATABASE_URL", "postgresql://app_user:app_password@localhost:54331/app_db")
DATA_DIR = "d:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/data-test"

async def ingest_file(conn, file_path, session_id):
    print(f"Ingesting {file_path} as {session_id}...")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    # Simple parsing: find speakers and text
    raw_text = "".join(lines)
    
    # Try to parse timestamps if available
    ts_file = os.path.join(DATA_DIR, "timestamp", os.path.basename(file_path))
    turns = []
    duration = 0
    
    if os.path.exists(ts_file):
        with open(ts_file, 'r', encoding='utf-8') as f:
            ts_lines = f.readlines()
            for i, line in enumerate(ts_lines):
                # Format: [00:00:00-00:00:03][Nữ] text
                match = re.match(r"\[(\d+:\d+:\d+)-(\d+:\d+:\d+)\]\[(.*?)\] (.*)", line)
                if match:
                    start_ts, end_ts, speaker, text = match.groups()
                    # Convert to seconds
                    def to_sec(ts):
                        h, m, s = map(int, ts.split(':'))
                        return h * 3600 + m * 60 + s
                    
                    s_sec = to_sec(start_ts)
                    e_sec = to_sec(end_ts)
                    duration = max(duration, e_sec)
                    turns.append({
                        "turn_index": i,
                        "speaker": speaker,
                        "time_start_sec": s_sec,
                        "time_end_sec": e_sec,
                        "text": text.strip()
                    })
    else:
        # Fallback for non-timestamped files
        for i, line in enumerate(lines):
            if ":" in line:
                parts = line.split(":", 1)
                speaker = parts[0].strip()
                text = parts[1].strip()
            elif " " in line:
                parts = line.split(" ", 1)
                speaker = parts[0].strip()
                text = parts[1].strip()
            else:
                speaker = "Unknown"
                text = line.strip()
            
            if text:
                turns.append({
                    "turn_index": i,
                    "speaker": speaker,
                    "time_start_sec": i * 10,
                    "time_end_sec": (i + 1) * 10,
                    "text": text
                })
        duration = len(turns) * 10

    # Hardcoded participants for each test scenario to enable entity/pronoun indexing
    participants_map = {
        "GT_01": [
            {"name": "トウノ", "gender": "male"},
            {"name": "シカズ", "gender": "male"},
            {"name": "梅田", "gender": "male"}
        ],
        "GT_02": [
            {"name": "中岡", "gender": "male", "organization": "バルテス"},
            {"name": "石田志保", "gender": "female", "organization": "アセットジャパン"},
            {"name": "志保", "gender": "female", "organization": "アセットジャパン"},
            {"name": "石田", "gender": "male", "organization": "アセットジャパン"}
        ],
        "GT_03": [
            {"name": "島田", "gender": "male"},
            {"name": "中原", "gender": "male", "organization": "アセットジャパン"}
        ],
        "GT_04": [
            {"name": "横堀", "gender": "male", "organization": "三菱UFJ銀行"},
            {"name": "中原凛花", "gender": "female"},
            {"name": "凛花", "gender": "female"},
            {"name": "中原", "gender": "female"}
        ],
        "GT_05": [
            {"name": "サカモト", "gender": "male"},
            {"name": "クマガイ", "gender": "male"}
        ],
        "GT_06": [
            {"name": "山下", "gender": "male"},
            {"name": "カセ", "gender": "male"}
        ],
        "GT_07": [
            {"name": "山下", "gender": "male"},
            {"name": "イシハラ", "gender": "male"}
        ],
        "GT_08": [
            {"name": "ツジ", "gender": "male"},
            {"name": "おのだ", "gender": "male"}
        ],
        "GT_09": [
            {"name": "伊藤", "gender": "male"},
            {"name": "山内", "gender": "male"}
        ],
    }
    participants = participants_map.get(session_id, [])
    import json
    participants_json = json.dumps(participants, ensure_ascii=False)

    # Insert into transcripts
    meeting_date = datetime(2026, 5, int(session_id.split('_')[1])) # Dummy date May X, 2026
    
    t_id = await conn.fetchval("""
        INSERT INTO transcripts (session_id, meeting_date, duration_seconds, raw_text, summary, participants)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id
    """, session_id, meeting_date, duration, raw_text, f"Summary for {session_id}", participants_json)
    
    # Insert turns
    for turn in turns:
        await conn.execute("""
            INSERT INTO chunks_turn (transcript_id, turn_index, speaker, time_start_sec, time_end_sec, text)
            VALUES ($1, $2, $3, $4, $5, $6)
        """, t_id, turn["turn_index"], turn["speaker"], turn["time_start_sec"], turn["time_end_sec"], turn["text"])

async def main():
    conn = await asyncpg.connect(DB_URL)
    try:
        # Clear existing data first
        print("Clearing old data...")
        await conn.execute("TRUNCATE transcripts CASCADE")
        
        files = [f for f in os.listdir(DATA_DIR) if f.startswith("GT_") and f.endswith(".txt")]
        for f in sorted(files):
            session_id = f.replace(".txt", "")
            await ingest_file(conn, os.path.join(DATA_DIR, f), session_id)
            
        print("Ingestion complete!")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
