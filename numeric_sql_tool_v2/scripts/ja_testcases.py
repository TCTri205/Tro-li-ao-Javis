"""Generate Japanese numeric test questions (txt) and run full pipeline → Excel."""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from itertools import product
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from numeric_sql_tool.cli import _get_llm_client
from numeric_sql_tool.config import Settings, require_database_url
from numeric_sql_tool.db_utils import create_pool
from numeric_sql_tool.pipeline import run_numeric_pipeline

DEFAULT_REFERENCE_DATE = date(2026, 5, 28)
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_QUESTIONS_TXT = ROOT / "db" / "numeric_sql_questions_ja.txt"
DEFAULT_EXCEL_OUT = ROOT / "db" / "numeric_sql_testcases_ja.xlsx"


def _seed_questions_ja() -> list[str]:
    return [
        "5月26日の会議は何について話し合いましたか？",
        "5月26日の定例会議で議論された主な議題は何ですか？",
        "5月26日の会議で、第2四半期の予算はいくらでしたか？",
        "5月26日の会議で第2四半期の予算について発言したのは誰ですか？",
        "音声認識プロジェクトについて話し合われた会議はいつですか？",
        "今月は会議が何回ありますか？",
        "私が参加した会議のうち、最も長かった会議はいつですか？",
        "佐藤さんは5月26日の会議で、第2四半期の予算について何分頃に発言しましたか？",
        "昨日、何か会議はありましたか？",
        "2026年5月に記録された会議は全部で何件ですか？",
        "5月15日の会議の所要時間は何秒ですか？",
        "5月20日の営業レビュー会議は何件カウントされますか？",
        "予算の話があった会議は何件ありますか？",
        "AiVoice Proのローンチについて話した会議を教えてください。",
        "話者ごとに、今月の会議数を集計してください。",
        "日ごとの会議件数を教えてください。今月でお願いします。",
        "今週の合計会議時間は何秒ですか？",
        "先月の平均会議時間を教えてください。",
        "一番短かった会議はどの日ですか？",
        "2026-05-26の会議はありますか？",
    ]


def _generated_questions_ja() -> list[str]:
    periods = ["今月", "今週", "先月", "今日", "昨日", "明日", "来週", "来月", "今年の5月"]
    dates = [
        "5月15日",
        "5月20日",
        "5月26日",
        "2026年5月15日",
        "2026年5月20日",
        "2026年5月26日",
        "2026-05-15",
        "2026-05-20",
        "2026-05-26",
    ]
    topics = [
        "予算",
        "音声認識",
        "ノイズキャンセリング",
        "エネルギー政策",
        "太陽光パネル",
        "AiVoice Pro",
        "マーケティング",
        "採用",
        "ローンチ",
        "クラウドコスト",
        "営業",
        "ベータ版",
    ]
    speakers = ["田中", "佐藤", "鈴木", "山田", "伊藤", "中村", "小林", "松本"]

    count_t = [
        "{p}の会議は何件ですか？",
        "{p}の会議件数を教えてください。",
        "{p}は何回会議がありましたか？",
        "{d}には会議が何件ありますか？",
        "{d}の会議は記録されていますか？",
        "私の{p}の会議数は？",
    ]
    exist_t = [
        "{p}、会議はありましたか？",
        "{p}、何か会議がありましたか？",
        "{d}に会議はありましたか？",
    ]
    duration_t = [
        "{p}の会議時間の合計は何秒ですか？",
        "{p}の合計会議時間を教えてください。",
        "{p}の平均会議時間は何秒ですか？",
        "{d}の会議時間は何秒ですか？",
        "{p}で最も長い会議の時間は？",
        "{p}で最短の会議時間は？",
        "私が参加した{p}で最も長かった会議は？",
        "私が参加した{p}で最も短い会議は？",
    ]
    group_t = [
        "{p}の会議数を日ごとに集計してください。",
        "{p}の会議時間を日別に教えてください。",
        "{p}の会議数を話者ごとに教えてください。",
        "{p}の会議時間を話者別に集計してください。",
        "{p}の会議件数をユーザーごとに集計してください。",
    ]
    topic_t = [
        "{topic}について話した会議は何件ですか？",
        "{topic}に関する会議は{p}何件ありますか？",
        "{topic}の話が出た会議を{p}教えてください。",
        "{d}の会議で{topic}について話しましたか？",
    ]
    skip_t = [
        "{speaker}は{d}の会議で予算について何分頃に発言しましたか？",
        "{d}の会議で{speaker}は何時頃に発言しましたか？",
        "{speaker}が{d}に発言したのは何秒目ですか？",
        "{d}の会議の要約を教えてください。",
        "{topic}について詳しく説明してください。",
        "{d}の会議で合意された内容は何ですか？",
    ]
    range_t = [
        "2026年5月15日から2026年5月26日までの会議は何件ですか？",
        "2026-05-15から2026-05-26までの合計会議時間は？",
        "5月15日から5月26日までの会議を日別に集計してください。",
    ]

    out: list[str] = []
    for tmpl, p in product(count_t, periods):
        out.append(tmpl.format(p=p, d=p, topic="", speaker=""))
    for tmpl, p in product(exist_t, periods):
        out.append(tmpl.format(p=p, d=p, topic="", speaker=""))
    for tmpl, p in product(duration_t, periods):
        out.append(tmpl.format(p=p, d=p, topic="", speaker=""))
    for tmpl, p in product(group_t, periods):
        out.append(tmpl.format(p=p, d=p, topic="", speaker=""))
    for d in dates:
        out.append(f"{d}の会議件数は何件ですか？")
        out.append(f"{d}の会議時間の合計は何秒ですか？")
        out.append(f"{d}に会議はありましたか？")
    for tmpl, topic in product(topic_t, topics):
        for p in ["今月", "先月", ""]:
            out.append(tmpl.format(topic=topic, p=p, d="5月26日", speaker=""))
    for tmpl, speaker in product(skip_t[:3], speakers[:4]):
        out.append(tmpl.format(speaker=speaker, d="5月26日", topic="予算", p=""))
    for tmpl in skip_t[3:]:
        out.append(tmpl.format(speaker="田中", d="5月26日", topic="予算", p="今月"))
    out.extend(range_t)
    return out


def build_question_list_ja(limit: int = 100) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for q in _seed_questions_ja() + _generated_questions_ja():
        q = q.strip()
        if not q or q in seen:
            continue
        seen.add(q)
        ordered.append(q)
        if len(ordered) >= limit:
            return ordered
    if len(ordered) < limit:
        raise RuntimeError(f"Only generated {len(ordered)} unique questions; need {limit}")
    return ordered


def write_questions_txt(path: Path, limit: int = 100) -> list[str]:
    questions = build_question_list_ja(limit)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(questions) + "\n", encoding="utf-8")
    print(f"Wrote {len(questions)} questions to {path}")
    return questions


def read_questions_txt(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]


def _sql_from_result(result) -> str:
    sql = result.metadata.get("sql")
    if sql:
        return str(sql)
    if result.metadata.get("skipped"):
        err = result.metadata.get("error", "")
        return f"SKIP (operator={result.operator}, target={result.target}) {err}".strip()
    return "SKIP (no SQL)"


async def _run_one(
    question: str,
    pool,
    llm_client,
    *,
    user_id: str,
    reference_date: date,
    statement_timeout_ms: int,
) -> dict[str, str]:
    try:
        result = await run_numeric_pipeline(
            question=question,
            db_pool=pool,
            llm_client=llm_client,
            user_id=user_id,
            reference_date=reference_date,
            allow_cross_user=False,
            statement_timeout_ms=statement_timeout_ms,
        )
        return {"question": question, "sql": _sql_from_result(result)}
    except Exception as exc:
        return {"question": question, "sql": f"ERROR: {exc}"}


async def run_pipeline_batch(
    questions: list[str],
    out_path: Path,
    *,
    user_id: str,
    reference_date: date,
    regex_only: bool,
    concurrency: int,
    delay_ms: int,
) -> None:
    settings = Settings.from_env()
    db_url = require_database_url(settings.database_url)
    llm_client = _get_llm_client(settings, regex_only)

    pool = await create_pool(db_url)
    sem = asyncio.Semaphore(max(1, concurrency))
    delay_s = max(0.0, delay_ms / 1000.0)

    async def guarded(q: str) -> dict[str, str]:
        async with sem:
            if delay_s:
                await asyncio.sleep(delay_s)
            return await _run_one(
                q,
                pool,
                llm_client,
                user_id=user_id,
                reference_date=reference_date,
                statement_timeout_ms=settings.statement_timeout_ms,
            )

    try:
        total = len(questions)
        print(
            f"Running pipeline on {total} questions "
            f"(regex_only={regex_only}, reference_date={reference_date}, user_id={user_id})"
        )
        rows = await asyncio.gather(*[guarded(q) for q in questions])
    finally:
        await pool.close()

    df = pd.DataFrame(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(out_path, index=False, sheet_name="testcases")
    skip_n = df["sql"].str.startswith("SKIP").sum()
    err_n = df["sql"].str.startswith("ERROR").sum()
    print(f"Wrote {len(df)} rows to {out_path} (skip={skip_n}, error={err_n})")


def cmd_generate(args: argparse.Namespace) -> None:
    write_questions_txt(args.out, limit=args.limit)


def cmd_run(args: argparse.Namespace) -> None:
    questions = read_questions_txt(args.questions)
    if not questions:
        raise RuntimeError(f"No questions in {args.questions}")
    asyncio.run(
        run_pipeline_batch(
            questions,
            args.excel_out,
            user_id=args.user_id,
            reference_date=date.fromisoformat(args.reference_date),
            regex_only=args.regex_only,
            concurrency=args.concurrency,
            delay_ms=args.delay_ms,
        )
    )


def cmd_all(args: argparse.Namespace) -> None:
    write_questions_txt(args.out, limit=args.limit)
    questions = read_questions_txt(args.out)
    asyncio.run(
        run_pipeline_batch(
            questions,
            args.excel_out,
            user_id=args.user_id,
            reference_date=date.fromisoformat(args.reference_date),
            regex_only=args.regex_only,
            concurrency=args.concurrency,
            delay_ms=args.delay_ms,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Japanese test questions (txt) + NumericSQL pipeline batch → Excel"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Write 100 JA questions to .txt")
    gen.add_argument("--out", type=Path, default=DEFAULT_QUESTIONS_TXT)
    gen.add_argument("--limit", type=int, default=100)
    gen.set_defaults(func=cmd_generate)

    run = sub.add_parser("run", help="Read .txt, run pipeline, write Excel")
    run.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS_TXT)
    run.add_argument("--excel-out", type=Path, default=DEFAULT_EXCEL_OUT)
    run.add_argument("--user-id", default=DEFAULT_USER_ID)
    run.add_argument("--reference-date", default=DEFAULT_REFERENCE_DATE.isoformat())
    run.add_argument("--regex-only", action="store_true", help="Disable LLM (default: LLM+regex)")
    run.add_argument("--concurrency", type=int, default=1, help="Parallel pipeline calls")
    run.add_argument("--delay-ms", type=int, default=1200, help="Pause between questions (ms)")
    run.set_defaults(func=cmd_run)

    all_cmd = sub.add_parser("all", help="generate + run")
    all_cmd.add_argument("--out", type=Path, default=DEFAULT_QUESTIONS_TXT)
    all_cmd.add_argument("--excel-out", type=Path, default=DEFAULT_EXCEL_OUT)
    all_cmd.add_argument("--limit", type=int, default=100)
    all_cmd.add_argument("--user-id", default=DEFAULT_USER_ID)
    all_cmd.add_argument("--reference-date", default=DEFAULT_REFERENCE_DATE.isoformat())
    all_cmd.add_argument("--regex-only", action="store_true")
    all_cmd.add_argument("--concurrency", type=int, default=1)
    all_cmd.add_argument("--delay-ms", type=int, default=1200)
    all_cmd.set_defaults(func=cmd_all)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
