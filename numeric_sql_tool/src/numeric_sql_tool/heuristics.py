from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

from .models import NumericIntent


_EXISTENCE_RE = re.compile(r"(会議).*(ありましたか|ありますか|あった|あります|ありました)|何か会議")
_TIMESTAMP_RE = re.compile(r"何分頃|何秒頃|いつ.*(発言|言)|何時.*(発言|言)")
_QUALITATIVE_RE = re.compile(
    r"何について|議題|要約|合意|アプローチ|発言したのは誰|詳しく説明|説明|"
    r"ローンチについて話した|ローンチについて話す|いくらでしたか|予算はいくら|"
    r"いくらですか|パーセント|原因|対策|対応策|アクション|曜日|天気|差は|比べ|対比|"
    r"どっち|どちら|どこですか|こんにちは|削除|できますか|おすすめ|"
    r"市場|内訳|募集|削減|消化率|多すぎる|指示しましたか|決まりましたか|"
    r"何億円|何社|何名|発言回数|何回発言|誰|何が決まり|リリース|予定日|"
    r"取得予定|締め切り|ローンチ日|理由|分析|問題|どんな|どのような|テーマ|冒頭|提案|反対|名前|社名|会社名|解決|アジェンダ|進捗|レポート|最適化|計画|決定事項|"
    r"参加者|参加企業|"
    r"効率的|トレンド|改善提案|根拠|推移|懸念|締めくくり|"
    r"フォローアップ|スキルセット|技術的な課題|承認されなかった|ペースについて|生産的|適切|課題|言及"
)
_UNSUPPORTED_OPS_RE = re.compile(
    r"割合|パーセント|比率|中央値|メジアン|パーセンタイル|週ごと|週別|曜日|土日|平日|営業日|"
    r"両方参加|より何件多|より何回多|前半|後半|"
    r"発言した合計時間|発言した平均|発言.*(分|秒|時間)|"
    r"先々月|第\d週|\d+週目|週目|上旬|中旬|下旬|年累計|直近\d+ヶ月|Q[1-4]|四半期|最終|最初|(?:今年|去年)(?!の?\d+月)|"
    r"\d+(分|時間|秒|日)(?:[をが])?(?:以上|超|以下|未満|より|ごと)|"
    r"\d+(回目|番目)に|\d+(回目|番目)の|二番目|2番目|"
    r"1日当たり|一日当たり|間隔|最も.*(週|月)|多かった週|の比"
)
_DURATION_MAX_RE = re.compile(r"最も長|一番長|最長|最大.*会議時間")
_DURATION_MIN_RE = re.compile(r"最も短|一番短|最短|最小.*会議時間")


def is_single_day_query(query: str) -> bool:
    if any(k in query for k in ["から", "〜", "まで"]):
        return False
    ja_dates = re.findall(r"\d{1,2}月\d{1,2}日", query)
    iso_dates = re.findall(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", query)
    if len(ja_dates) + len(iso_dates) > 1:
        return False
    if any(k in query for k in ["今日", "本日", "昨日", "明日"]):
        return True
    if len(ja_dates) == 1:
        return True
    if len(iso_dates) == 1:
        return True
    return False


def heuristic_numeric_intent(query: str) -> NumericIntent:
    q_lower = query.lower().strip()
    if q_lower in {"会議", "こんにちは"}:
        return NumericIntent(operator="skip", target="none", group_by="none")

    # Skip qualitative/semantic questions or detailed timestamps
    if _TIMESTAMP_RE.search(query) or _QUALITATIVE_RE.search(query):
        return NumericIntent(operator="skip", target="none", group_by="none")

    # Skip unsupported operations and complex temporal expressions
    if _UNSUPPORTED_OPS_RE.search(query):
        return NumericIntent(operator="skip", target="none", group_by="none")

    # Skip general "When" questions that aren't about min/max duration
    if "いつですか" in query and not re.search(r"最も|一番", query):
        return NumericIntent(operator="skip", target="none", group_by="none")

    # Skip 2 periods comparison questions
    periods = ["今月", "先月", "来月", "今週", "先週", "来週", "今日", "昨日", "明日"]
    period_count = sum(1 for p in periods if p in query)
    if period_count > 1:
        return NumericIntent(operator="skip", target="none", group_by="none")

    # Skip multiple metrics questions
    has_count = any(k in query for k in ["件数", "何件", "何回", "回数", "会議数"])
    has_duration = any(k in query for k in ["時間", "所要時間", "合計時間", "平均時間", "総時間", "何分", "何秒"])
    if has_count and has_duration:
        return NumericIntent(operator="skip", target="none", group_by="none")

    # Skip "which meeting" questions unless they ask about duration/extremes
    if ("どれ" in query and "どれくらい" not in query) or "どの" in query:
        if not any(k in query for k in ["長", "短", "時間", "期間"]):
            return NumericIntent(operator="skip", target="none", group_by="none")

    # Skip scheduling intents
    if any(k in query for k in ["ミーティングをしたい", "会議をしたい", "予約したい"]):
        return NumericIntent(operator="skip", target="none", group_by="none")

    operator = "sum"
    if _DURATION_MAX_RE.search(query):
        operator = "max"
    elif _DURATION_MIN_RE.search(query):
        operator = "min"
    elif re.search(r"平均", query):
        operator = "avg"
    elif re.search(r"最大|一番多", query):
        operator = "max"
    elif re.search(r"最小|一番少", query):
        operator = "min"
    elif re.search(r"何件|何回|件数|会議数", query):
        operator = "count"

    target = "meeting_count"
    if _DURATION_MAX_RE.search(query) or _DURATION_MIN_RE.search(query):
        target = "duration_seconds"
    elif re.search(r"何時間|所要時間|会議時間|合計時間|長さ|総時間|平均時間|何秒|何分", query):
        target = "duration_seconds"
    elif re.search(r"何件|会議数|会議件数", query) or _EXISTENCE_RE.search(query):
        target = "meeting_count"
        operator = "count"

    group_by = "none"
    if re.search(r"ユーザーごと|ユーザー別", query):
        group_by = "user_id"
    elif re.search(r"日ごと|日別", query):
        group_by = "day"
    elif re.search(r"話者ごと|話者別", query):
        group_by = "speaker"

    if is_single_day_query(query) and group_by == "day":
        group_by = "none"

    return NumericIntent(operator=operator, target=target, group_by=group_by)


def resolve_date_range(question: str, reference_date: date) -> tuple[date | None, date | None]:
    # 1. Try standard YYYY-MM-DD
    matches = re.findall(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", question)
    if matches:
        dates = [date(int(y), int(m), int(d)) for y, m, d in matches]
        if len(dates) == 1:
            return dates[0], dates[0]
        return min(dates), max(dates)

    # 2. Try YYYY年MM月DD日
    matches_ja_full = re.findall(r"(\d{4})年(\d{1,2})月(\d{1,2})日", question)
    if matches_ja_full:
        dates = [date(int(y), int(m), int(d)) for y, m, d in matches_ja_full]
        if len(dates) == 1:
            return dates[0], dates[0]
        return min(dates), max(dates)

    # 3. Try MM月DD日 (use reference_date.year)
    matches_ja_md = re.findall(r"(\d{1,2})月(\d{1,2})日", question)
    if matches_ja_md:
        dates = [date(reference_date.year, int(m), int(d)) for m, d in matches_ja_md]
        if len(dates) == 1:
            return dates[0], dates[0]
        return min(dates), max(dates)

    # 4. Try MM月 (without Day, e.g. 5月)
    matches_m = re.findall(r"(\d{1,2})月(?!日)", question)
    if matches_m:
        m = int(matches_m[0])
        start = date(reference_date.year, m, 1)
        _, last_day = calendar.monthrange(reference_date.year, m)
        end = date(reference_date.year, m, last_day)
        return start, end

    if any(key in question for key in ["今日", "本日"]):
        return reference_date, reference_date
    if "昨日" in question:
        d = reference_date - timedelta(days=1)
        return d, d
    if "明日" in question:
        d = reference_date + timedelta(days=1)
        return d, d

    weekday = reference_date.weekday()
    week_start = reference_date - timedelta(days=weekday)
    week_end = week_start + timedelta(days=6)

    if "今週" in question:
        return week_start, week_end
    if "先週" in question:
        return week_start - timedelta(days=7), week_end - timedelta(days=7)
    if "来週" in question:
        return week_start + timedelta(days=7), week_end + timedelta(days=7)

    if "今月" in question:
        start = date(reference_date.year, reference_date.month, 1)
        _, last_day = calendar.monthrange(reference_date.year, reference_date.month)
        end = date(reference_date.year, reference_date.month, last_day)
        return start, end

    if "先月" in question:
        if reference_date.month == 1:
            year, month = reference_date.year - 1, 12
        else:
            year, month = reference_date.year, reference_date.month - 1
        start = date(year, month, 1)
        _, last_day = calendar.monthrange(year, month)
        end = date(year, month, last_day)
        return start, end

    if "来月" in question:
        if reference_date.month == 12:
            year, month = reference_date.year + 1, 1
        else:
            year, month = reference_date.year, reference_date.month + 1
        start = date(year, month, 1)
        _, last_day = calendar.monthrange(year, month)
        end = date(year, month, last_day)
        return start, end

    return None, None


def enforce_intent_invariants(intent: NumericIntent, query: str) -> NumericIntent:
    """Apply strict invariants that must hold true regardless of LLM output.
    
    Invariant 1: Single-day queries never need GROUP BY day.
    """
    if is_single_day_query(query) and intent.group_by == "day":
        intent.group_by = "none"
    return intent

