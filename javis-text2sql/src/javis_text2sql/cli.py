from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from javis_text2sql.config import SAMPLE_DATA_DIR, Settings, require_database_url
from javis_text2sql.db.admin import apply_migrations, create_pool, seed_entity_aliases, verify_views, seed_golden_queries
from javis_text2sql.etl.samples import ingest_sample_files
from javis_text2sql.eval.runner import evaluate_sample_fixtures, write_report
from javis_text2sql.llm.fixture import FixtureLLMClient


async def _cmd_migrate(args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    database_url = args.database_url or require_database_url(settings.database_url)
    applied = await apply_migrations(database_url)
    print(json.dumps({"applied": applied}, ensure_ascii=False, indent=2))


async def _cmd_seed(args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    database_url = args.database_url or require_database_url(settings.database_url)
    count = await seed_entity_aliases(database_url)
    golden_count = await seed_golden_queries(database_url)
    print(json.dumps({"seeded_entity_aliases": count, "seeded_golden_queries": golden_count}, ensure_ascii=False, indent=2))


async def _cmd_ingest_samples(args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    database_url = args.database_url or require_database_url(settings.database_url)
    
    from javis_text2sql.llm import get_llm_client
    if args.fixture_llm:
        client = FixtureLLMClient()
    else:
        client = get_llm_client(settings)

    pool = await create_pool(database_url)
    try:
        meeting_ids = await ingest_sample_files(pool, client, sample_dir=Path(args.sample_dir))
    finally:
        await pool.close()
    print(json.dumps({"ingested_meeting_ids": meeting_ids}, ensure_ascii=False, indent=2))


async def _cmd_verify(args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    database_url = args.database_url or require_database_url(settings.database_url)
    report = await verify_views(database_url)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


async def _cmd_eval(args: argparse.Namespace) -> None:
    settings = Settings.from_env()
    from javis_text2sql.llm import get_llm_client
    if args.fixture_llm:
        client = FixtureLLMClient()
    else:
        client = get_llm_client(settings)

    report = await evaluate_sample_fixtures(sample_dir=Path(args.sample_dir), llm_client=client)
    if args.output:
        write_report(report, Path(args.output))
    print(json.dumps(report, ensure_ascii=False, indent=2, default=list))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="javis-text2sql")
    sub = parser.add_subparsers(dest="command", required=True)

    migrate = sub.add_parser("migrate")
    migrate.add_argument("--database-url")
    migrate.set_defaults(handler=_cmd_migrate)

    seed = sub.add_parser("seed")
    seed.add_argument("--database-url")
    seed.set_defaults(handler=_cmd_seed)

    ingest = sub.add_parser("ingest-samples")
    ingest.add_argument("--database-url")
    ingest.add_argument("--sample-dir", default=str(SAMPLE_DATA_DIR))
    ingest.add_argument("--fixture-llm", action="store_true")
    ingest.set_defaults(handler=_cmd_ingest_samples)

    verify = sub.add_parser("verify")
    verify.add_argument("--database-url")
    verify.set_defaults(handler=_cmd_verify)

    evaluate = sub.add_parser("eval")
    evaluate.add_argument("--sample-dir", default=str(SAMPLE_DATA_DIR))
    evaluate.add_argument("--output")
    evaluate.add_argument("--fixture-llm", action="store_true")
    evaluate.set_defaults(handler=_cmd_eval)
    return parser


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(args.handler(args))


if __name__ == "__main__":
    main()
