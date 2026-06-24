"""Export 100 numeric test questions and the SQL NumericSQL would run (regex-only intent)."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from itertools import product
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from numeric_sql_tool.heuristics import heuristic_numeric_intent, resolve_date_range
from numeric_sql_tool.pipeline import build_numeric_sql

DEFAULT_REFERENCE_DATE = date(2026, 5, 28)
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_OUT = ROOT / "db" / "numeric_sql_testcases.xlsx"


def _seed_questions() -> list[str]:
    """Curated cases from the chatbot test sheet and common numeric patterns."""
    return [
        "5月26の会議は何についてだったのですか？",
        "5月26日の会議で、第2四半期の予算はいくらでしたか？",
        "5月26日の会議で第2四半期の予算について発言したのは誰でしたか？",
        "音声認識プロジェクトについて話し合われた会議はどれですか？",
        "今月は会議が何回ありますか？",
        "私がこれまで参加した中で、最も長かった会議は何でしたか？",
        "佐藤氏は5月26日の会議で、第2四半期の予算について何分頃に発言しましたか？",
        "昨日、何か会議はありましたか？",
        "Cuộc họp ngày 26 tháng 5 bàn về vấn đề gì?",
        "Tại cuộc họp ngày 26 tháng 5, ngân sách cho quý 2 là bao nhiêu?",
        "Trong tháng này tôi có bao nhiêu cuộc meeting?",
        "Cuộc họp có thời lượng dài nhất của tôi là bao nhiêu?",
        "Ngày hôm qua tôi có cuộc họp nào không?",
    ]


def _generated_questions() -> list[str]:
    periods_ja = [
        "今月",
        "今週",
        "先月",
        "今日",
        "昨日",
        "明日",
        "来週",
        "来月",
        "",
    ]
    periods_vi = [
        "trong tháng này",
        "tuần này",
        "tháng trước",
        "hôm nay",
        "hôm qua",
    ]
    dates = [
        "5月15日",
        "5月20日",
        "5月26日",
        "2026-05-15",
        "2026-05-20",
        "2026-05-26",
        "2026-05-01から2026-05-31",
    ]

    count_templates_ja = [
        "{p}の会議は何件ですか？",
        "{p}の会議数を教えてください。",
        "{p}は会議が何回ありましたか？",
        "{d}の会議はありますか？",
        "{d}に会議は何件ありますか？",
    ]
    duration_templates_ja = [
        "{p}の会議時間の合計は何秒ですか？",
        "{p}の合計会議時間は？",
        "{p}の平均会議時間は？",
        "最も長かった会議はいつですか？{p}",
        "一番短い会議はどれですか？{p}",
        "{p}で最も長い会議の時間は？",
        "{p}で最短の会議時間は？",
    ]
    group_templates_ja = [
        "{p}の会議数を日ごとに集計してください。",
        "{p}の会議時間を日別で教えて。",
        "{p}の会議数を話者ごとに教えて。",
        "{p}の会議時間を話者別に集計してください。",
    ]
    skip_templates = [
        "佐藤は5月26日の会議で予算について何分頃に発言しましたか？",
        "5月26日に予算の話は何時頃でしたか？",
        "田中さんがいつ発言したか教えてください。",
        "AiVoice Proのローンチ日はいつですか？",
        "会議の要約を教えてください。",
    ]

    out: list[str] = []
    for tmpl, p in product(count_templates_ja, periods_ja):
        out.append(tmpl.format(p=p, d=p))
    for tmpl, p in product(duration_templates_ja, periods_ja):
        out.append(tmpl.format(p=p, d=p))
    for tmpl, p in product(group_templates_ja, periods_ja):
        out.append(tmpl.format(p=p, d=p))
    for d in dates:
        out.append(f"{d}の会議件数は？")
        out.append(f"{d}の会議時間の合計は？")
    for p in periods_vi:
        out.append(f"{p} có bao nhiêu cuộc họp?")
        out.append(f"Tổng thời lượng meeting {p} là bao nhiêu giây?")
    out.extend(skip_templates)
    return out


def build_question_list(limit: int = 100) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for q in _seed_questions() + _generated_questions():
        q = q.strip()
        if not q or q in seen:
            continue
        seen.add(q)
        ordered.append(q)
        if len(ordered) >= limit:
            return ordered
    return ordered


def sql_for_question(question: str, reference_date: date) -> str:
    intent = heuristic_numeric_intent(question)
    sql = build_numeric_sql(intent)
    if sql is not None:
        return sql

    date_start, date_end = resolve_date_range(question, reference_date)
    return (
        "SKIP — không sinh SQL numeric "
        f"(operator={intent.operator}, target={intent.target}, group_by={intent.group_by}; "
        f"date_start={date_start}, date_end={date_end})"
    )


def export_excel(
    out_path: Path,
    *,
    limit: int,
    reference_date: date,
) -> None:
    questions = build_question_list(limit)
    rows = [
        {
            "question": q,
            "sql": sql_for_question(q, reference_date),
        }
        for q in questions
    ]
    df = pd.DataFrame(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(out_path, index=False, sheet_name="testcases")
    print(f"Wrote {len(df)} rows to {out_path}")
    print(
        "Params khi chạy thật: $1=user_id, $2=date_start, $3=date_end, $4=context_filter "
        f"(reference_date={reference_date.isoformat()}, user_id={DEFAULT_USER_ID})"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Export numeric SQL test cases to Excel")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--reference-date", default=DEFAULT_REFERENCE_DATE.isoformat())
    args = parser.parse_args()
    ref = date.fromisoformat(args.reference_date)
    export_excel(args.out, limit=args.limit, reference_date=ref)


if __name__ == "__main__":
    main()
