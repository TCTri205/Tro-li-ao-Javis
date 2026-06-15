# Data loading

**Use the leader dump** (`dump-app_db-202606041640.sql` at project root), not the legacy `*.sql` INSERT files here.

```powershell
docker compose up -d
python scripts/restore_db.py
```

This loads 13 transcripts (9 `ingest-media-gt_*` from `data_docs` + 3 meetings + 1 sample), passages, turns, and chat history with the same UUIDs and summaries as production.

Optional: `python scripts/generate_meeting_sql.py` regenerates simplified INSERT files for debugging only.
