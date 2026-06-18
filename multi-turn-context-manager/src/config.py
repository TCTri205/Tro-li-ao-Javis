import re

# Session Pattern (Supports GT, SESSION, SESS, RECORD, TR, etc.)
SESSION_PATTERN = r'\b(?:GT|SESSION|SESS|RECORD|TR)[-_]?\d+\b'
SESSION_REGEX = re.compile(SESSION_PATTERN, re.IGNORECASE)

# Pipeline Keywords (Decoupled System & Domain keywords)
SQL_SYSTEM_KEYWORDS = [
    "選択", "カウント", "平均", "時間", "通話", "日付", "何時", "誰", "秒", "分", "通話時間", 
    "だれ", "何秒", "何分", "件数", "何件", "いつ", "何日", "伝言", "メンバ", "メンバー", "参加者",
    "担当者", "名前", "会社", "企業"
]
SQL_DOMAIN_KEYWORDS = []

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
MAX_CACHE_SLOTS = 3
CACHE_TTL_WEB = 3600  # 1 hour
CACHE_TTL_SQL = 86400 # 24 hours
