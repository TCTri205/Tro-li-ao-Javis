from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

from .models import NumericIntent


_EXISTENCE_RE = re.compile(
    r"(会議|会話|電話|連絡|やり取り|話題|発言).*(ありましたか|ありますか|あった|あります|ありました|出ましたか|記録されていますか|記録されていませんか|存在しますか|存在するか|ないですか|なかったですか|なかったのですか|ありませんでしたか|ありませんか)|"
    r"何か(会議|会話|電話|連絡|話題)"
)
_TIMESTAMP_RE = re.compile(r"何分頃|何秒頃|いつ.*(発言|言)|何時.*(発言|言)")
_QUALITATIVE_RE = re.compile(
    r"何について|議題|要約|合意|アプローチ|発言したのは誰|詳しく説明|説明|"
    r"ローンチについて話した|ローンチについて話す|いくらでしたか|予算はいくら|"
    r"いくらですか|パーセント|原因|対策|対応策|アクション|曜日|天気|差は|比べ|対比|"
    r"どっち|どちら|どこですか|こんにちは|削除|できますか|おすすめ|"
    r"市場|内訳|募集|削減|消化率|多すぎる|指示しましたか|決まりましたか|"
    r"何億円|何社|何名|誰|何が決まり|リリース|予定日|"
    r"取得予定|締め切り|ローンチ日|理由|分析|問題|どんな|どのような|テーマ|冒頭|提案|反対|社名|解決|アジェンダ|進捗|レポート|最適化|計画|決定事項|"
    r"参加者|参加企業|"
    r"効率的|トレンド|改善提案|根拠|推移|懸念|締めくくり|"
    r"フォローアップ|スキルセット|技術的な課題|承認されなかった|ペースについて|生産的|適切|課題|"
    r"まとめて|一覧|目的|結果|要旨|内容|やり取り|時系列|フロー|マニュアル|規程|ルール|規則|基準|定義|指示|確認内容|確認事項"
)
_UNSUPPORTED_OPS_RE = re.compile(
    r"割合|パーセント|比率|中央値|メジアン|パーセンタイル|曜日|土日|平日|営業日|"
    r"両方参加|より何件多|より何回多|前半|後半|"
    r"先々月|第\d週|\d+週目|週目|上旬|中旬|下旬|年累計|直近\d+ヶ月|Q[1-4]|四半期|最終|最初|(?:今年|去年)(?!の?\d+月)|"
    r"\d+(分|時間|秒|日)(?:[をが])?(?:以上|超|以下|未満|より|ごと)|"
    r"\d+(回目|番目)に|\d+(回目|番目)の|二番目|2番目|"
    r"1日当たり|一日当たり|間隔|最も.*(週|月)|多かった週|の比"
)
_DURATION_MAX_RE = re.compile(r"最も長|一番長|最長|最大.*(会議|通話|会話)時間")
_DURATION_MIN_RE = re.compile(r"最も短|一番短|最短|最小.*(会議|通話|会話)時間")

_DURATION_TARGET_RE = re.compile(
    r"何時間|所要時間|通話時間|発話時間|会話時間|会議時間|合計時間|総時間|平均時間|発言時間|長さ|何秒|何分"
)


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

    # Custom fine-grained quantitative queries check
    # 1. Speaking time
    if "発話時間" in query or "発言時間" in query:
        speaker_match = re.search(r"([^、\s]+?)(?:様)?の(?:平均)?発[話言]時間", query)
        is_overall = "総発話" in query or "全体の発話" in query or "通話の発話" in query or "会議の発話" in query or not speaker_match
        if is_overall:
            operator = "avg" if "平均" in query else "sum"
            return NumericIntent(
                operator=operator,
                target="speaking_time",
                group_by="none",
                speaker=None
            )
        elif speaker_match:
            speaker = speaker_match.group(1)
            for sep in ["における", "での", "の", "で", "に", "から", "と", "が", "は"]:
                if sep in speaker and not speaker.startswith("SPEAKER"):
                    speaker = speaker.split(sep)[-1]
            if any(k in speaker for k in ["会議", "電話", "通話", "月", "日", "今日", "昨日"]) or ("様" not in query and "speaker" not in query.lower()):
                return NumericIntent(operator="skip", target="none", group_by="none")
            operator = "avg" if "平均" in query else "sum"
            return NumericIntent(
                operator=operator,
                target="speaking_time",
                group_by="none",
                speaker=speaker
            )

    # 2. Turn count
    if "何回発言" in query or re.search(r"発言.*何回|何回.*発言", query):
        speaker_match = re.search(r"([^、\s]+?)(?:様)?は(?:会話の中で)?何回発言", query)
        if speaker_match:
            speaker = speaker_match.group(1)
            for sep in ["における", "での", "の", "で", "に", "から", "と", "が", "は"]:
                if sep in speaker and not speaker.startswith("SPEAKER"):
                    speaker = speaker.split(sep)[-1]
            if any(k in speaker for k in ["会議", "電話", "通話", "月", "日", "今日", "昨日"]) or ("様" not in query and "speaker" not in query.lower()):
                return NumericIntent(operator="skip", target="none", group_by="none")
            return NumericIntent(
                operator="count",
                target="turn_count",
                group_by="none",
                speaker=speaker
            )

    # 3. Mention count
    is_mention_count = False
    if "何回言及" in query or "言及された回数" in query or "言及された件数" in query or "言及された数" in query or "言及数は" in query or "言及は何回" in query or ("言及" in query and "何回" in query):
        is_mention_count = True
    elif "会社名の確認は何回" in query:
        is_mention_count = True
    elif "折り返し連絡に関する発言は何回" in query or ("折り返し" in query and "発言" in query and "何回" in query):
        is_mention_count = True

    if is_mention_count:
        quote_match = re.search(r"「([^」]+)」", query)
        if quote_match:
            keyword = quote_match.group(1)
        elif "会社名" in query:
            keyword = "会社名"
        elif "折り返し" in query:
            keyword = "折り返し"
        else:
            name_match = re.search(r"([^、\s]+?)(?:様の名前|様|の名前)は?が?については?何回言及", query)
            if name_match:
                keyword = name_match.group(1)
            else:
                keyword = None
        return NumericIntent(
            operator="count",
            target="mention_count",
            group_by="none",
            keyword=keyword
        )

    # Skip speaker-specific queries if they don't contain a valid speaker identifier (様 or speaker)
    if any(k in query for k in ["発言", "発話"]):
        if not any(k in query for k in ["話者", "ごと", "別"]):
            if "様" not in query and "speaker" not in query.lower():
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
    has_count = any(k in query for k in ["件数", "何件", "何回", "回数", "会議数", "総数", "の数"])
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

    # Strict numeric check
    is_numeric = False
    if _DURATION_MAX_RE.search(query) or _DURATION_MIN_RE.search(query):
        is_numeric = True
    elif re.search(r"何件|何回|件数|回数|会議数|総数|の数", query):
        is_numeric = True
    elif _DURATION_TARGET_RE.search(query):
        is_numeric = True
    elif "どのくらい" in query and any(k in query for k in ["時間", "長", "短"]):
        is_numeric = True
    elif _EXISTENCE_RE.search(query):
        is_qualitative_existence = False
        if any(w in query for w in ["様", "さん", "話題", "伝言", "連絡", "用件", "内容", "物件"]):
            is_qualitative_existence = True
        if not is_qualitative_existence:
            if is_single_day_query(query):
                meeting_words = ["会議", "電話", "会話", "通話", "打ち合わせ"]
                if any(w + "はあり" in query or w + "があり" in query or w + "の履歴" in query or w + "記録" in query or w + "存在" in query or w + "は記録" in query or w + "がな" in query or w + "が一" in query for w in meeting_words):
                    if not any(w in query for w in ["質問", "発言", "確認", "合意", "否定", "断", "説明", "用件", "要望"]):
                        is_numeric = True
            else:
                is_numeric = True

    if not is_numeric:
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
    elif re.search(r"何件|何回|件数|回数|会議数|総数|の数", query):
        operator = "count"

    target = "meeting_count"
    if _DURATION_MAX_RE.search(query) or _DURATION_MIN_RE.search(query):
        target = "duration_seconds"
    elif _DURATION_TARGET_RE.search(query):
        target = "duration_seconds"
    elif "どのくらい" in query and "時間" in query:
        target = "duration_seconds"
    elif re.search(r"何件|何回|件数|回数|会議数|総数|の数", query) or _EXISTENCE_RE.search(query):
        target = "meeting_count"
        operator = "count"

    group_by = "none"
    if re.search(r"ユーザーごと|ユーザー別", query):
        group_by = "user_id"
    elif re.search(r"日ごと|日別", query):
        group_by = "day"
    elif re.search(r"週ごと|週別|毎週", query):
        group_by = "week"
    elif re.search(r"月ごと|月別|毎月", query):
        group_by = "month"
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
    if intent.operator in {"skip", "none"} or intent.target in {"none", "time_start_sec"}:
        return intent

    if is_single_day_query(query) and intent.group_by == "day":
        intent.group_by = "none"

    # Invariant 2: speaker speaking time
    if "発話時間" in query or "発言時間" in query:
        speaker_match = re.search(r"([^、\s]+?)(?:様)?の(?:平均)?発[話言]時間", query)
        is_overall = "総発話" in query or "全体の発話" in query or "通話の発話" in query or "会議の発話" in query or not speaker_match
        if is_overall:
            intent.speaker = None
            intent.target = "speaking_time"
            intent.operator = "avg" if "平均" in query else "sum"
        elif speaker_match:
            speaker = speaker_match.group(1)
            for sep in ["における", "での", "の", "で", "に", "から", "と", "が", "は"]:
                if sep in speaker and not speaker.startswith("SPEAKER"):
                    speaker = speaker.split(sep)[-1]
            if any(k in speaker for k in ["会議", "電話", "通話", "月", "日", "今日", "昨日"]) or ("様" not in query and "speaker" not in query.lower()):
                return NumericIntent(operator="skip", target="none", group_by="none")
            intent.speaker = speaker
            intent.target = "speaking_time"
            intent.operator = "avg" if "平均" in query else "sum"

    # Invariant 3: turn count
    if "何回発言" in query or re.search(r"発言.*何回|何回.*発言", query):
        speaker_match = re.search(r"([^、\s]+?)(?:様)?は(?:会話の中で)?何回発言", query)
        if speaker_match:
            speaker = speaker_match.group(1)
            if "の" in speaker and not speaker.startswith("SPEAKER"):
                speaker = speaker.split("の")[-1]
            intent.speaker = speaker
            intent.target = "turn_count"
            intent.operator = "count"

    # Invariant 4: mention count
    is_mention_count = False
    if "何回言及" in query or "言及された回数" in query or "言及された件数" in query or "言及された数" in query or "言及数は" in query or "言及は何回" in query or ("言及" in query and "何回" in query):
        is_mention_count = True
    elif "会社名の確認は何回" in query:
        is_mention_count = True
    elif "折り返し連絡に関する発言は何回" in query or ("折り返し" in query and "発言" in query and "何回" in query):
        is_mention_count = True

    if is_mention_count:
        quote_match = re.search(r"「([^」]+)」", query)
        if quote_match:
            keyword = quote_match.group(1)
        elif "会社名" in query:
            keyword = "会社名"
        elif "折り返し" in query:
            keyword = "折り返し"
        else:
            name_match = re.search(r"([^、\s]+?)(?:様の名前|様|の名前)は?が?については?何回言及", query)
            if name_match:
                keyword = name_match.group(1)
            else:
                keyword = None
        intent.keyword = keyword
        intent.target = "mention_count"
        intent.operator = "count"

    # Invariant 5: Top-N limit
    limit_match = re.search(
        r"上位\s*(\d+)|トップ\s*(\d+)|ベスト\s*(\d+)|ワースト\s*(\d+)|(\d+)\s*件の最長|(\d+)\s*件の最短|最長.*?(\d+)\s*件|最短.*?(\d+)\s*件",
        query
    )
    if limit_match:
        for g in limit_match.groups():
            if g is not None:
                intent.limit = int(g)
                break

    return intent

