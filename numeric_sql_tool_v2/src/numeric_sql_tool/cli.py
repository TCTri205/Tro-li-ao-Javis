from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

# Leader dump (dump-app_db-202606041640.sql) uses this test user/project.
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_DUMP = Path(__file__).resolve().parents[2] / "dump-app_db-202606041640.sql"

from .config import Settings, require_database_url
from .db_utils import apply_sql_dir, apply_sql_file, create_pool
from .groq_client import GroqClient
from .pipeline import run_numeric_pipeline
from .llm_client import LLMClient


def _get_llm_client(settings: Settings, regex_only: bool) -> LLMClient | None:
    if regex_only:
        return None
    if settings.llm_provider.lower() != "groq":
        raise RuntimeError(f"Unsupported LLM provider: {settings.llm_provider}")
    if not settings.groq_api_keys:
        raise RuntimeError("GROQ_API_KEYS is required for live LLM")
    return GroqClient(api_keys=settings.groq_api_keys, model=settings.groq_model)


async def _cmd_init_db(args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    db_url = args.database_url or require_database_url(settings.database_url)
    schema_path = Path(args.schema)

    pool = await create_pool(db_url)
    try:
        async with pool.acquire() as conn:
            await apply_sql_file(conn, schema_path)
    finally:
        await pool.close()
    print(json.dumps({"applied": schema_path.name}, ensure_ascii=False, indent=2))


def _sanitize_dump_for_pg15(dump_path: Path) -> Path:
    """Adapt pg_dump 17 / owner postgres for PostgreSQL 15 + app_user in Docker."""
    skip_fragments = (
        "transaction_timeout",
        "OWNER TO postgres",
        "REVOKE USAGE ON SCHEMA public FROM PUBLIC",
    )
    lines = dump_path.read_text(encoding="utf-8").splitlines()
    if not any(any(frag in line for frag in skip_fragments) for line in lines):
        return dump_path
    cleaned = "\n".join(
        line for line in lines if not any(frag in line for frag in skip_fragments)
    )
    out = dump_path.parent / ".restore_dump_sanitized.sql"
    out.write_text(cleaned + "\n", encoding="utf-8")
    return out


def _cmd_restore_db(args: argparse.Namespace) -> None:
    dump_path = _sanitize_dump_for_pg15(Path(args.dump))
    reset_path = Path(args.reset)
    if not dump_path.is_file():
        raise RuntimeError(f"Dump not found: {dump_path}")

    if args.docker:
        base = [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            args.db_user,
            "-d",
            args.db_name,
        ]
        compose_dir = dump_path.parent if (dump_path.parent / "docker-compose.yml").is_file() else dump_path.parent.parent
        if not (compose_dir / "docker-compose.yml").is_file():
            compose_dir = Path(__file__).resolve().parents[2]
    else:
        base = ["psql", "-v", "ON_ERROR_STOP=1", "-U", args.db_user, "-d", args.db_name]
        compose_dir = None

    def run_sql_file(sql_path: Path) -> None:
        cmd = [*base, "-f", "-"]
        print("+", " ".join(cmd), "<", sql_path)
        with sql_path.open("r", encoding="utf-8") as fh:
            if compose_dir is not None:
                proc = subprocess.run(cmd, stdin=fh, cwd=str(compose_dir), check=False)
            else:
                proc = subprocess.run(cmd, stdin=fh, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"psql failed ({proc.returncode}) for {sql_path}")

    if not args.no_reset:
        run_sql_file(reset_path)
    run_sql_file(dump_path)
    print(json.dumps({"restored": dump_path.name, "reset": not args.no_reset}, ensure_ascii=False, indent=2))


async def _cmd_load_data(args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    db_url = args.database_url or require_database_url(settings.database_url)
    data_dir = Path(args.data_dir)

    pool = await create_pool(db_url)
    try:
        async with pool.acquire() as conn:
            applied = await apply_sql_dir(conn, data_dir)
    finally:
        await pool.close()
    print(json.dumps({"applied": applied}, ensure_ascii=False, indent=2))


async def _cmd_batch(args: argparse.Namespace) -> None:
    from pathlib import Path as PathLib

    questions_path = PathLib(args.questions_file)
    lines = questions_path.read_text(encoding="utf-8").splitlines()
    questions = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    if not questions:
        raise RuntimeError(f"No questions in {questions_path}")

    settings = Settings.from_env()
    db_url = args.database_url or require_database_url(settings.database_url)
    llm_client = _get_llm_client(settings, args.regex_only)
    reference_date = date.fromisoformat(args.reference_date) if args.reference_date else date.today()

    import asyncio

    import pandas as pd

    from .pipeline import run_numeric_pipeline

    pool = await create_pool(db_url)
    sem = asyncio.Semaphore(max(1, args.concurrency))
    delay_s = max(0.0, args.delay_ms / 1000.0)
    rows: list[dict[str, str]] = []

    async def run_one(question: str) -> dict[str, str]:
        async with sem:
            if delay_s:
                await asyncio.sleep(delay_s)
            try:
                result = await run_numeric_pipeline(
                    question=question,
                    db_pool=pool,
                    llm_client=llm_client,
                    user_id=args.user_id,
                    reference_date=reference_date,
                    allow_cross_user=args.allow_cross_user,
                    statement_timeout_ms=settings.statement_timeout_ms,
                )
                sql = result.metadata.get("sql")
                if sql:
                    sql_text = str(sql)
                elif result.metadata.get("skipped"):
                    err = result.metadata.get("error", "")
                    sql_text = f"SKIP (operator={result.operator}, target={result.target}) {err}".strip()
                else:
                    sql_text = "SKIP (no SQL)"
                return {"question": question, "sql": sql_text}
            except Exception as exc:
                return {"question": question, "sql": f"ERROR: {exc}"}

    try:
        rows = await asyncio.gather(*[run_one(q) for q in questions])
    finally:
        await pool.close()

    out_path = PathLib(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_excel(out_path, index=False, sheet_name="testcases")
    print(
        json.dumps(
            {
                "questions_file": str(questions_path),
                "out": str(out_path),
                "count": len(rows),
                "regex_only": args.regex_only,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


async def _cmd_numeric(args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    question = (args.question or sys.stdin.read()).strip()
    if not question:
        raise RuntimeError("Question is required via --question or stdin")

    reference_date = date.fromisoformat(args.reference_date) if args.reference_date else date.today()
    date_start = date.fromisoformat(args.date_start) if args.date_start else None
    date_end = date.fromisoformat(args.date_end) if args.date_end else None

    db_url = args.database_url or require_database_url(settings.database_url)
    llm_client = _get_llm_client(settings, args.regex_only)

    pool = await create_pool(db_url)
    try:
        result = await run_numeric_pipeline(
            question=question,
            db_pool=pool,
            llm_client=llm_client,
            user_id=args.user_id,
            reference_date=reference_date,
            date_start=date_start,
            date_end=date_end,
            allow_cross_user=args.allow_cross_user,
            statement_timeout_ms=settings.statement_timeout_ms,
        )
    finally:
        await pool.close()

    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="numeric-sql-tool")
    sub = parser.add_subparsers(dest="command", required=True)

    init_db = sub.add_parser("init-db")
    init_db.add_argument("--database-url")
    init_db.add_argument("--schema", default=str(Path("db") / "schema.sql"))
    init_db.set_defaults(handler=_cmd_init_db)

    load_data = sub.add_parser("load-data", help="Load legacy INSERT SQL from db/data (prefer restore-db)")
    load_data.add_argument("--database-url")
    load_data.add_argument("--data-dir", default=str(Path("db") / "data"))
    load_data.set_defaults(handler=_cmd_load_data)

    restore_db = sub.add_parser(
        "restore-db",
        help="Restore leader pg_dump (schema + data, COPY format)",
    )
    restore_db.add_argument("--dump", default=str(DEFAULT_DUMP))
    restore_db.add_argument("--reset", default=str(Path("db") / "reset_all.sql"))
    restore_db.add_argument("--db-user", default="app_user")
    restore_db.add_argument("--db-name", default="app_db")
    restore_db.add_argument("--docker", action="store_true", default=True)
    restore_db.add_argument("--no-docker", dest="docker", action="store_false")
    restore_db.add_argument("--no-reset", action="store_true")
    restore_db.set_defaults(handler=_cmd_restore_db)

    numeric = sub.add_parser("numeric")
    numeric.add_argument("--question")
    numeric.add_argument("--user-id", default=DEFAULT_USER_ID)
    numeric.add_argument("--reference-date", help="YYYY-MM-DD")
    numeric.add_argument("--date-start", help="YYYY-MM-DD")
    numeric.add_argument("--date-end", help="YYYY-MM-DD")
    numeric.add_argument("--database-url")
    numeric.add_argument("--allow-cross-user", action="store_true")
    numeric.add_argument("--regex-only", action="store_true")
    numeric.set_defaults(handler=_cmd_numeric)

    batch = sub.add_parser("batch", help="Run pipeline for each question in a text file → Excel")
    batch.add_argument("--questions-file", default=str(Path("db") / "numeric_sql_questions_ja.txt"))
    batch.add_argument("--out", default=str(Path("db") / "numeric_sql_testcases_ja.xlsx"))
    batch.add_argument("--user-id", default=DEFAULT_USER_ID)
    batch.add_argument("--reference-date", help="YYYY-MM-DD (default: today)")
    batch.add_argument("--database-url")
    batch.add_argument("--allow-cross-user", action="store_true")
    batch.add_argument("--regex-only", action="store_true", help="Use regex only, no LLM")
    batch.add_argument("--concurrency", type=int, default=1)
    batch.add_argument(
        "--delay-ms",
        type=int,
        default=1200,
        help="Pause between questions (reduces Groq 429 rate limits)",
    )
    batch.set_defaults(handler=_cmd_batch)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    handler = args.handler
    if asyncio.iscoroutinefunction(handler):
        asyncio.run(handler(args))
    else:
        handler(args)


if __name__ == "__main__":
    main()
