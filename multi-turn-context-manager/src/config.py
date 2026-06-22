import re

# Session Pattern (Supports GT, SESSION, SESS, RECORD, TR, etc.)
SESSION_PATTERN = r'\b(?:GT|SESSION|SESS|RECORD|TR)[-_]?\d+(?![a-zA-Z0-9])'
SESSION_REGEX = re.compile(SESSION_PATTERN, re.IGNORECASE | re.ASCII)

# Pipeline Keywords (Decoupled System & Domain keywords)
SQL_SYSTEM_KEYWORDS = [
    "選択", "カウント", "平均", "時間", "通話", "日付", "何時", "誰", "秒", "分", "通話時間", 
    "だれ", "何秒", "何分", "件数", "何件", "いつ", "何日", "伝言", "メンバ", "メンバー", "参加者",
    "担当者", "名前", "会社", "企業"
]
SQL_DOMAIN_KEYWORDS = ["賃料", "坪単価", "成約", "仲介料", "敷金", "礼金", "賃貸", "管理費", "売買"]

# Heuristic SQL translation query classification keywords
HEURISTIC_SQL_DETAIL = [
    "詳細", "具体の内容", "話したこと", "内容", "中身", "伝言", "発言", "メッセージ", 
    "予定", "約束", "打ち合わせ", "言いました", "言っていました"
]
HEURISTIC_SQL_DURATION = [
    "時間", "秒", "分", "どれくらい", "期間", "長さ", "つうわ"
]
HEURISTIC_SQL_MEMBERS = [
    "誰", "参加者", "話者", "相手", "メンバ", "メンバー", "名前", "担当者"
]
HEURISTIC_SQL_COMPARE = [
    "比較", "くらべ", "対比"
]

RAG_SYSTEM_KEYWORDS = [
    "要約", "内容", "詳細", "発言", "翻訳", "ドキュメント", "ファイル", "テキスト", "何を話した", 
    "訳", "相談", "面談", "打ち合わせ", "議事録", "ログ", "目的", "理由", "共通", "比較"
]
RAG_DOMAIN_KEYWORDS = [
    "内見", "契約", "物件", "管理", "入居", "重説", "重要事項", "IT重説", "重要事項説明", 
    "仲介", "媒介", "登記", "抵当", "賃貸", "売買", "敷金", "礼金", "管理費", "修繕", "告知事項"
]

WEB_KEYWORDS = [
    "天気", "株価", "ニュース", "ネット", "検索", "グーグル", "株"
]

# Direct-Answer Path Keywords
DIRECT_PATH_SHOW_DETAILS = ["内容", "詳細", "発言", "会話", "テキスト", "ログ", "履歴", "中身", "書き起こし", "スクリプト"]
DIRECT_PATH_SPECIFIC_FIELDS = ["コード", "番号", "ID番号", "パスワード", "価格", "金額", "いつ", "予定", "時間", "何時", "何日"]

# Combined keyword lists exported to the rest of the application
SQL_KEYWORDS = SQL_SYSTEM_KEYWORDS + SQL_DOMAIN_KEYWORDS
RAG_KEYWORDS = RAG_SYSTEM_KEYWORDS + RAG_DOMAIN_KEYWORDS

# SQL Response Formatting
SQL_FRIENDLY_KEYS = {
    "duration": "通話時間",
    "meeting_date": "日付",
    "date": "日付",
    "summary": "要約",
    "speaker": "話者",
    "participants": "参加者"
}

# Cache Settings
MAX_CACHE_SLOTS = 5
CACHE_TTL_WEB = 3600  # 1 hour
CACHE_TTL_SQL = 86400 # 24 hours
