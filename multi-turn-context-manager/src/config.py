import re

# Session Pattern (GT_XX)
SESSION_PATTERN = r'GT_\d+'
SESSION_REGEX = re.compile(SESSION_PATTERN, re.IGNORECASE)

# Pipeline Keywords (Real Estate Focus)
SQL_KEYWORDS = [
    "選択", "カウント", "平均", "時間", "通話", "日付", "何時", "誰", "秒", "分", "通話時間", 
    "だれ", "何秒", "何分", "件数", "何件", "いつ", "何日"
]

RAG_KEYWORDS = [
    "要約", "内容", "詳細", "発言", "翻訳", "ドキュメント", "ファイル", "テキスト", "何を話した", 
    "訳", "内見", "契約", "相談", "面談", "打ち合わせ", "議事録", "ログ", "物件", "管理", "入居"
]

WEB_KEYWORDS = [
    "天気", "株価", "ニュース", "ネット", "検索", "グーグル", "株"
]

# Note: "三菱" (Mitsubishi) removed from WEB_KEYWORDS to avoid conflict with GT_04 (Mitsubishi UFJ Bank).

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
