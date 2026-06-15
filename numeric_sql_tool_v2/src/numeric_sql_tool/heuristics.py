from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

from .models import NumericIntent


# ── Timestamp / qualitative patterns ─────────────────────────────────────────
_EXISTENCE_RE = re.compile(r"(会議).*(ありましたか|ありますか|あった|あります|ありました)|何か会議")
_TIMESTAMP_RE = re.compile(r"何分頃|何秒頃|いつ.*(発言|言)|何時.*(発言|言)")

# ── Turn-level patterns (checked BEFORE qualitative RE) ─────────────────────

# Q-mention: 何回言及 / 何度言及 / 何回行われ / 何回ありました (phrase count in turns)
_MENTION_COUNT_RE = re.compile(
    r"(何回|何度|回数).{0,15}(言及|呼ばれ|出てき|登場|行われ|行なわれ|ありました|確認)(されましたか|しましたか|ですか|か)?|"
    r"(言及|登場|呼ばれ).{0,15}(何回|何度|回数)"
)

# Q-turn-avg-duration: SPEAKER X / named person の平均発話時間
_TURN_AVG_DURATION_RE = re.compile(
    r"(SPEAKER\s*\d+|話者\s*\d+|[ぁ-ん一-龯ァ-ンa-zA-Z\w]{1,12}(さん|様|さま)?)\s*の"
    r".{0,30}(平均|average).{0,15}(発話|発言|話す|スピーチ).{0,10}(時間|秒|duration)|"
    r"(平均|average).{0,15}(発話|発言).{0,10}(時間|秒).{0,30}(SPEAKER\s*\d+|話者\s*\d+)"
)

# Q-turn-count: SPEAKER X は何回発言 / named person は何回発言
_TURN_COUNT_SPEAKER_RE = re.compile(
    r"(SPEAKER\s*\d+|話者\s*\d+).{0,20}(何回|何度|回数|何度).{0,15}(発言|話した|喋った|発話|utterance)|"
    r"(何回|何度|回数).{0,15}(発言|話した|喋った|発話).{0,30}(SPEAKER\s*\d+|話者\s*\d+)"
)

# Q-distinct-speakers: 何人が発言 (count distinct speakers in a call)
_DISTINCT_SPEAKERS_RE = re.compile(
    r"何人.{0,15}(発言|話した|参加|喋った|発話)|"
    r"(発言|参加).{0,15}何人"
)

# Q-speaker-argmax: 最も長い発言は誰 / 一番長い発言は誰
_LONGEST_TURN_SPEAKER_RE = re.compile(
    r"(最も|一番).{0,5}(長|大きい).{0,10}(発言|発話|turn).{0,15}(誰|speaker|話者)|"
    r"(誰).{0,15}(最も|一番).{0,5}(長|大きい).{0,10}(発言|発話)"
)

# Q-speaker-argmin: 最も短い発言は誰
_SHORTEST_TURN_SPEAKER_RE = re.compile(
    r"(最も|一番).{0,5}(短|小さい).{0,10}(発言|発話|turn).{0,15}(誰|speaker|話者)|"
    r"(誰).{0,15}(最も|一番).{0,5}(短|小さい).{0,10}(発言|発話)"
)

# Q-most-talkative: 最も多く発言したのは誰
_MOST_TALKATIVE_RE = re.compile(
    r"(最も|一番).{0,5}(多く|多い).{0,10}(発言|話した|喋った|発話).{0,15}(誰|speaker|話者)|"
    r"(誰).{0,15}(最も|一番).{0,5}(多く|多い).{0,10}(発言|話した)|"
    r"最も多く発言"
)

# Total call duration (matches calls asking about call/meeting duration)
_CALL_TOTAL_DURATION_RE = re.compile(
    r"(総通話時間|合計通話時間|通話時間.{0,5}合計|電話.{0,5}時間.{0,5}合計|"
    r"電話.{0,5}総.{0,5}時間|call.{0,5}duration|total.{0,5}duration|"
    r"通話全体の時間|通話時間|合計.{0,5}時間|会議の長さ|会議は何分)"
)

# ── Hard SKIP: semantic / qualitative / non-numeric ──────────────────────────

# Pattern group A: summary / explanation / QA / contextual questions
_SEMANTIC_A_RE = re.compile(
    r"何について|議題|要約|合意|アプローチ|詳しく説明|"
    r"ローンチについて話した|ローンチについて話す|いくらでしたか|予算はいくら|"
    r"いくらですか|パーセント|原因|対策|対応策|曜日|天気|差は|比べ|対比|"
    r"どっち|こんにちは|削除|できますか|おすすめ|"
    r"市場|内訳|募集|削減|消化率|多すぎる|指示しましたか|決まりましたか|"
    r"何億円|何社|何名|リリース|予定日|"
    r"取得予定|締め切り|ローンチ日|分析|どんな|テーマ|冒頭|提案|反対|解決|アジェンダ|進捗|レポート|最適化|決定事項|"
    r"効率的|トレンド|改善提案|根拠|推移|懸念|締めくくり|"
    r"フォローアップ|スキルセット|技術的な課題|承認されなかった|ペースについて|生産的|適切"
)

# Pattern group B: question words asking for content description
_SEMANTIC_B_RE = re.compile(
    # "どのような" / "どのように" + anything
    r"どのような|どのように|どういった|どのくらいの内容|"
    # "which / what" (予定) : どの予定/どの会議/どれ (semantic)
    r"どの(予定|会議|打ち合わせ|件|案件|物件|話題|日時|場面|タイミング)|"
    # どちらが (comparison — semantic)
    r"どちら(が|の).{0,15}(多く|発言|発話|回数|参加)|"
    # asking "who" in semantic sense
    r"誰が(参加|主催|担当|所属|発言した内容|説明した|発言した理由)|"
    r"誰に.{0,10}(依頼|取り次ぎ|転送|伝えた|連絡した)|"
    # と発言したのは誰ですか (who said X)
    r"と(発言|言|述べ|話し|確認|答え).{0,10}(のは誰|したのは誰|は誰)|"
    # 誰について確認するために / 誰について問い合わせ (who is being inquired about)
    r"誰について.{0,20}(確認|問い合わせ|連絡|依頼)|"
    # 伝言を依頼したのは誰 / 依頼したのは誰
    r"(依頼|伝言|お願い|申し出).{0,10}したのは誰|"
    # "what for / why" questions
    r"何のために|なぜ|何を.{0,10}(確認|説明|依頼|伝え|告げ|報告|提案|相談|伝言|案内)|"
    # asking for content: 内容/用件/経緯/目的/結果/状況/進捗/対応/流れ
    r"(内容|用件|目的|経緯|経過|状況|対応|流れ|進捗|背景|概要|詳細|判断|措置|確認事項|アクションアイテム).{0,10}(を|が|は|について|に関して)?(教えて|まとめ|説明|整理|示して|知りたい|聞かせ|お願い|ください|ますか|でしょうか)|"
    # asking for information: 〜を教えてください / 〜について教えて
    r"(について|に関して|に関する).{0,30}(教えて|まとめ|説明|示して|整理|知りたい|お願い|ください)|"
    r"(を|が)(教えて|まとめ|整理|示して)(ください|いただけ|もらえ|ほしい)|"
    # summary markers
    r"(要約|まとめ|サマリー|要旨|概要|要点).{0,15}(して|ください|お願い)|"
    r"(して|お).{0,10}(まとめ|ください|お願い)|"
    # "list / describe topics"
    r"(トピック|話題|テーマ|議題).{0,15}(一覧|リスト|教えて)|"
    # organizational / HR / business rule questions
    r"(社内ルール|業務マニュアル|対応フロー|規定|条項|ポリシー|セキュリティ|定義|実施基準|基準|勤務管理|開示基準|業務運営規程|連携基準|取り扱い|対応ポリシー)|"
    # asking for contact info / personnel info
    r"(連絡先情報|連絡先|電話番号|組織情報|連絡窓口|担当者情報|登録).{0,20}(教えて|まとめ|整理|ください|情報)|"
    # asking which chapter/section of manual
    r"(章|条項|どこに記載|に記載されて)|"
    # call history / log listing
    r"(通話履歴|会話履歴|履歴).{0,20}(表示|見せ|すべて|一覧)|"
    # recent contact check (semantic lookup)
    r"最近の.{0,40}(通話|会話|連絡).{0,40}(ありましたか|ありますか|連絡はありましたか|連絡はありますか|話題は出|伝言や連絡は|連絡は)|"
    # uncertain / unresolved / unclear info
    r"確認できなかった|不確実な情報|未解決|未確認|未確定|"
    # asking for explicit/clear answer in context
    r"明確な(回答|答え|説明|指示).{0,10}(はありましたか|ありましたか|ありますか)|"
    # 誰に依頼 / 誰に取り次ぎ (asking who was delegated)
    r"誰に(依頼|取り次ぎ|お願い|伝言|案内|紹介)(しましたか|をしましたか|を依頼しましたか)?|"
    # remaining unresolved / needed follow-up items (semantic)
    r"(追加で|さらに).{0,10}(確認|調整|対応).{0,5}が必要.{0,10}(事項|こと)|"
    r"(まだ|まだ\s*).{0,5}確認できていなかった|"
    # negative / denial response check (semantic content question)
    r"(断ったり|否定したり|反対したり).{0,10}(発言|言|述べ).{0,10}(はありましたか|ありましたか)|"
    # reason / cause questions
    r"(理由|原因).{0,10}(は何|何と).{0,10}(説明|言|述べ)(されましたか|ましたか|ますか)|"
    # unresolved items phrased as 事項は何
    r"確認できていなかった.{0,10}(事項|こと|情報).{0,10}(は何|ですか)|"
    # compound questions with content (いくつ + 内容)
    r"いくつの(確認事項|項目|内容|ポイント)|"
    # date range existence check (semantic — checking if meetings happened)
    r"\d+月\d+日から.{0,30}までの間に.{0,50}(ありましたか|ありますか)|"
    # definition / meaning of terms
    r"とは何を指して|"
    # recent topic check
    r"最近の(会話|通話).{0,30}(話題は出|出ましたか|ましたか)"
)

# Pattern group C: speaker exchange / timeline / who said what
_SEMANTIC_C_RE = re.compile(
    r"やり取り|時系列|発言箇所|抽出し|発言のみ|発言だけ|どのような.{0,15}(依頼|説明|案内|対応)|"
    r"何を(確認|説明|依頼|伝え|案内|報告|相談|提案).{0,15}(しましたか|していましたか)|"
    r"誰が(発言|言|述べ|説明|案内|依頼|告げ|話し|確認|提案).{0,15}(しましたか|ました|でしたか)|"
    # と説明したのは誰ですか / と発言したのは誰ですか (who said X verbatim)
    r"と(説明|発言|回答|述べ|言|答え|話し).{0,10}(したのは誰|のは誰|は誰|たのは誰)|"
    r"(問題点|懸念|障害|不安|制約).{0,15}(は何|ありましたか|ますか)|"
    r"(対応方針|方針|結論|合意).{0,15}(になりましたか|決まりましたか|どのような)|"
    r"(調整|交渉|やり取り|話し合い|確認).{0,15}(時系列|をまとめ|を整理|について)"
)

# Pattern group D: unsupported operations
_UNSUPPORTED_OPS_RE = re.compile(
    r"割合|比率|中央値|メジアン|パーセンタイル|週ごと|週別|土日|平日|営業日|"
    r"両方参加|より何件多|より何回多|前半|後半|"
    r"先々月|第\d週|\d+週目|週目|上旬|中旬|下旬|年累計|直近\d+ヶ月|Q[1-4]|四半期|最終|最初|(?:今年|去年)(?!の?\d+月)|"
    r"\d+(分|時間|秒|日)(?:[をが])?(?:以上|超|以下|未満|より|ごと)|"
    r"\d+(回目|番目)に|\d+(回目|番目)の|二番目|2番目|"
    r"1日当たり|一日当たり|間隔|多かった週|の比"
)

# Meeting-level max/min duration
_DURATION_MAX_RE = re.compile(r"最も長|一番長|最長|最大.*会議時間")
_DURATION_MIN_RE = re.compile(r"最も短|一番短|最短|最小.*会議時間")


# ── Helper functions ──────────────────────────────────────────────────────────

def _extract_speaker(query: str) -> str | None:
    """Extract speaker label like 'SPEAKER 1' from query."""
    m = re.search(r"(SPEAKER\s*\d+)", query, re.IGNORECASE)
    if m:
        raw = m.group(1)
        normalized = re.sub(r"(SPEAKER)\s*(\d+)", r"SPEAKER \2", raw, flags=re.IGNORECASE)
        return normalized.upper()
    m2 = re.search(r"話者\s*(\d+)", query)
    if m2:
        return f"SPEAKER {m2.group(1)}"
    # Named person before の平均発話時間
    m3 = re.search(
        r"([ぁ-ん一-龯ァ-ンa-zA-Z\w]{1,8})(さん|様|さま)?\s*の.{0,20}(平均|average).{0,10}(発話|発言)",
        query,
    )
    if m3:
        return m3.group(1)  # return the person's name as speaker filter hint
    return None


# Date patterns to exclude from entity extraction
_DATE_PATTERN_RE = re.compile(r"^\d{4}年\d{1,2}月\d{1,2}日$|^\d{4}-\d{1,2}-\d{1,2}$")


def _extract_entity(query: str) -> str | None:
    """Extract entity name to count mentions for. Returns None for date strings."""
    # First priority: quoted phrase like 「14日水曜日」が何回
    m2 = re.search(r"「([^」]+)」.{0,10}(何回|何度|回数|言及)", query)
    if m2:
        return m2.group(1)

    # Entity before の名前は何回言及
    m3 = re.search(
        r"([ぁ-ん一-龯ァ-ン]{1,8}[一-龯]{0,4})(さん|様|さま)?\s*の名前.{0,10}(何回|何度|言及)",
        query,
    )
    if m3 and not _DATE_PATTERN_RE.match(m3.group(1)):
        return m3.group(1)

    # Entity + に関する/についての発言は何回
    m4 = re.search(
        r"([ぁ-ん一-龯ァ-ン]{1,8}[一-龯]{0,4})(さん|様|さま|氏)?"
        r"(について|に関して|に関する).{0,10}(発言|言及|確認).{0,10}(何回|何度|回数)",
        query,
    )
    if m4 and not _DATE_PATTERN_RE.match(m4.group(1)):
        return m4.group(1)

    # Entity+honorific + については/は + 何回言及/確認/行われ
    # Require at least 1 kanji to avoid matching date digits
    m = re.search(
        r"([ぁ-ん一-龯ァ-ン]{1,4}[一-龯]{1,6}|[A-Za-z]{2,12})(さん|様|さま|氏)?"
        r"(?:については?|は|に関して|の).{0,15}(何回|何度|回数|言及|呼ばれ|登場|出てき|確認|行われ|ありました)",
        query,
    )
    if m and not _DATE_PATTERN_RE.match(m.group(1)):
        return m.group(1)

    return None


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


def _is_semantic(query: str) -> bool:
    """Return True if the query requires semantic / content understanding (→ SKIP)."""
    return bool(
        _TIMESTAMP_RE.search(query)
        or _SEMANTIC_A_RE.search(query)
        or _SEMANTIC_B_RE.search(query)
        or _SEMANTIC_C_RE.search(query)
    )


def heuristic_numeric_intent(query: str) -> NumericIntent:
    q_lower = query.lower().strip()
    if q_lower in {"会議", "こんにちは"}:
        return NumericIntent(operator="skip", target="none", group_by="none")

    # ── 1. Turn-level detectors (checked BEFORE semantic / qualitative regexes) ──

    # Q7-type: most talkative speaker
    if _MOST_TALKATIVE_RE.search(query):
        return NumericIntent(operator="max", target="speaker_name", group_by="speaker")

    # Q4-type: speaker with longest single turn
    if _LONGEST_TURN_SPEAKER_RE.search(query):
        return NumericIntent(operator="max", target="speaker_name", group_by="none")

    # Q5-type: speaker with shortest single turn
    if _SHORTEST_TURN_SPEAKER_RE.search(query):
        return NumericIntent(operator="min", target="speaker_name", group_by="none")

    # Q6-type: turn count for a specific SPEAKER N
    if _TURN_COUNT_SPEAKER_RE.search(query):
        speaker = _extract_speaker(query)
        return NumericIntent(operator="count", target="turn_count", speaker_filter=speaker)

    # Q3-type: average turn duration for a named person or SPEAKER N
    if _TURN_AVG_DURATION_RE.search(query):
        speaker = _extract_speaker(query)
        return NumericIntent(operator="avg", target="turn_duration", speaker_filter=speaker)

    # distinct speakers: 何人が発言 (count distinct speakers)
    if _DISTINCT_SPEAKERS_RE.search(query):
        # "何について確認していましたか" part is semantic → SKIP only the semantic part
        # But the 何人が発言 part is numeric — return distinct_speakers
        # NOTE: These questions are compound (何人発言＋何について確認) → SKIP to RAG
        # because the second part is qualitative. Return SKIP.
        return NumericIntent(operator="skip", target="none", group_by="none")

    # Q1-type: entity / phrase mention count
    if _MENTION_COUNT_RE.search(query):
        entity = _extract_entity(query)
        return NumericIntent(operator="count", target="mention_count", entity_filter=entity)

    # ── 2. Semantic / qualitative SKIP ──────────────────────────────────────

    if _is_semantic(query):
        return NumericIntent(operator="skip", target="none", group_by="none")

    # Skip unsupported operations
    if _UNSUPPORTED_OPS_RE.search(query):
        return NumericIntent(operator="skip", target="none", group_by="none")

    # Skip general "When" questions
    if "いつですか" in query and not re.search(r"最も|一番", query):
        return NumericIntent(operator="skip", target="none", group_by="none")

    # Skip 2-period comparison
    periods = ["今月", "先月", "来月", "今週", "先週", "来週", "今日", "昨日", "明日"]
    period_count = sum(1 for p in periods if p in query)
    if period_count > 1:
        return NumericIntent(operator="skip", target="none", group_by="none")

    # Skip multi-metric queries (count AND duration together)
    has_count = any(k in query for k in ["件数", "何件", "何回", "回数", "会議数"])
    has_duration = any(k in query for k in ["時間", "所要時間", "合計時間", "平均時間", "総時間", "何分", "何秒"])
    if has_count and has_duration:
        return NumericIntent(operator="skip", target="none", group_by="none")

    # Skip scheduling intents
    if any(k in query for k in ["ミーティングをしたい", "会議をしたい", "予約したい"]):
        return NumericIntent(operator="skip", target="none", group_by="none")

    # ── 3. Meeting-level aggregation ─────────────────────────────────────────

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
    elif _CALL_TOTAL_DURATION_RE.search(query):
        target = "duration_seconds"
        operator = "sum"
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
