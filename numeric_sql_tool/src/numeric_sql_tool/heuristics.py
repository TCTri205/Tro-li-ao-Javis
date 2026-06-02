from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

from .models import NumericIntent


_EXISTENCE_RE = re.compile(r"(会議).*(ありましたか|ありますか|あった|あります|ありました)|何か会議")
_TIMESTAMP_RE = re.compile(r"何分頃|何秒頃|いつ.*(発言|言)|何時.*(発言|言)")
_QUALITATIVE_RE = re.compile(
    r"何について|議題|要約|合意された内容|発言したのは誰|詳しく説明|"
    r"ローンチについて話した|ローンチについて話す|いくらでしたか|予算はいくら"
)
_DURATION_MAX_RE = re.compile(r"最も長|一番長|最長|最大.*会議時間")
_DURATION_MIN_RE = re.compile(r"最も短|一番短|最短|最小.*会議時間")


def heuristic_numeric_intent(query: str) -> NumericIntent:
    # Skip qualitative/semantic questions or detailed timestamps
    if _TIMESTAMP_RE.search(query) or _QUALITATIVE_RE.search(query):
        return NumericIntent(operator="skip", target="none", group_by="none")

    # Skip general "When" questions that aren't about min/max duration
    if "いつですか" in query and not re.search(r"最も|一番", query):
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
    elif re.search(r"何時間|所要時間|会議時間|合計時間", query):
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
    return NumericIntent(operator=operator, target=target, group_by=group_by)


def resolve_date_range(question: str, reference_date: date) -> tuple[date | None, date | None]:
    matches = re.findall(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", question)
    if matches:
        dates = [date(int(y), int(m), int(d)) for y, m, d in matches]
        if len(dates) == 1:
            return dates[0], dates[0]
        return min(dates), max(dates)

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
