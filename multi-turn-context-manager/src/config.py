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

# Heuristic SQL translation query classification keywords (DURAION & MEMBERS only, DETAIL moved to LLM)
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

# Direct-Answer Path Exclude Keywords
DIRECT_PATH_EXCLUDE_REASONING_KEYWORDS = ["理由", "背景", "なぜ", "解説", "説明", "どうして", "原因", "分析"]
DIRECT_PATH_EXCLUDE_ROLES_KEYWORDS = ["誰から", "誰に", "発信", "受信", "かけた", "受けた", "どちらから", "誰宛", "立場", "役割", "目的", "用件"]

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

# Embedding model version
EMBEDDING_MODEL_VERSION = 'multilingual-e5-small'

# Token Limits
ADAPTIVE_TOKENS_REASONING = 1500
ADAPTIVE_TOKENS_CHAT = 300
ADAPTIVE_TOKENS_DEFAULT = 800

def get_adaptive_max_tokens(model_name: str) -> int:
    # Determine max_tokens adaptively based on model type (Reasoning vs Chat)
    if not model_name:
        return ADAPTIVE_TOKENS_DEFAULT
    model_name_lower = model_name.lower()
    
    # Check reasoning model patterns
    if any(p in model_name_lower for p in ["reasoning", "-r1", "o1-", "o3-", "qwq"]):
        return ADAPTIVE_TOKENS_REASONING
        
    # Check chat model patterns
    if any(p in model_name_lower for p in ["flash", "llama", "mini", "haiku", "qwen", "gpt", "claude"]):
        return ADAPTIVE_TOKENS_CHAT
        
    return ADAPTIVE_TOKENS_DEFAULT

# ----------------- Parameterized Refactored Heuristics -----------------

# Embedding Distance Thresholds
SEMANTIC_CONFIDENCE_THRESHOLD = 0.35
SEMANTIC_SHIFT_THRESHOLD = 0.55
SEMANTIC_AMBIGUITY_GAP = 0.65

# Circuit Breaker Configuration
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 3
CIRCUIT_BREAKER_COOLDOWN_SECONDS = 30
CIRCUIT_BREAKER_TIMEOUT_SECONDS = 30.0
CIRCUIT_BREAKER_TIMEOUT_OVERRIDE = 60.0

# Entity Interaction Decay & Increment
ENTITY_DECAY_FACTOR = 0.5
ENTITY_INCREMENT = 1.0

# EMA Cache Embedding Parameters
EMA_ALPHA = 0.8
EMA_MAX_UPDATES = 5
EMA_DISTANCE_THRESHOLD = 0.5
EMA_SIMID_SAFEGUARD = 0.60

# Japanese Honorific Suffixes & Suffix classification
HONORIFIC_SUFFIXES = ["さん", "様", "さま", "君", "くん", "ちゃん", "氏", "殿"]
HONORIFIC_SUFFIX_PATTERN = r'(さん|様|さま|君|くん|ちゃん|氏|殿)$'

FEMALE_SUFFIXES = (
    "子", "美", "香", "花", "華", "奈", "菜", "乃", "莉", "里", 
    "理", "梨", "咲", "織", "恵", "絵", "江", "穂", "沙", "紗", 
    "羽", "和", "音", "凛", "杏", "楓", "葵"
)
MALE_SUFFIXES = (
    "郎", "朗", "夫", "男", "雄", "介", "助", "佑", "佐", "人", 
    "斗", "翔", "登", "太", "也", "哉", "弥", "樹", "輝", "木", 
    "司", "嗣", "馬", "吾", "悟", "将", "正", "雅", "洋", "博", 
    "宏", "浩"
)

# Pronoun Lists
PRONOUNS = [
    "それ", "あれ", "これ", "そちら", "あちら", "こちら", 
    "彼", "彼女", "彼ら", "彼女ら", "その人", "あの人", "この人",
    "さっき", "先ほど", "さきほど", "先程", "前回の", "さっきの", "先ほどの",
    "このファイル", "そのファイル", "あのファイル",
    "このドキュメント", "そのドキュメント", "あのドキュメント",
    "この通話", "その通話", "あの通話", "先ほどの通話", "さっきの通話",
    "この会話", "その会話", "あの会話", "先ほどの会話", "さっきの会話",
    "この打ち合わせ", "その打ち合わせ", "あの打ち合わせ", "先ほどの打ち合わせ", "さっきの打ち合わせ",
    "この連絡", "その連絡", "あの連絡", "先ほどの連絡", "さっきの連絡",
    "その件", "あの件", "この件", "その話", "あの話", "この話",
    "そのcall", "このcall", "あのcall", "さっきのcall", "先ほどのcall",
    "その", "この", "あの", "その物件", "この物件", "あの物件",
    "同物件", "同通話", "同氏", "同社", "お二人", "二人", "双方", "両者"
]

SINGULAR_PRONOUNS = ["彼", "彼女", "それ", "その人", "先ほどの担当者", "先ほどの", "その件", "その話"]

PLURAL_PRONOUN_PATTERN = r'(彼ら|彼女ら|ら\b|方々|お二人|二人|双方|両者)'

PRONOUN_WORDS = {"あの人", "その人", "この人", "彼", "彼女", "それ", "あれ", "こちら", "そちら", "あちら", "これ", "担当者", "お二人", "二人", "双方", "両者", "通話", "会話"}

SWITCH_KEYWORDS = ["やっぱり", "別の話", "キャンセル", "スキップ", "忘れて"]
SWITCH_KEYWORDS_PATTERN = re.compile(r'(やっぱり|別の話|キャンセル|スキップ|忘れて)', re.IGNORECASE)

# Entity Extraction Types
ALLOWED_ENTITY_TYPES = {'meeting_transcript', 'person', 'document', 'sql_result'}
ENTITY_TYPE_MAPPING = {
    'company': 'document',
    'organization': 'document',
    'object': 'document',
    'thing': 'document',
    'location': 'document',
    'user': 'person',
    'human': 'person',
    'employee': 'person'
}

# Blocklist of common/generic display names that must be filtered out during indexing
COMMON_PRONOUNS_BLOCKLIST = {
    "その通話", "その会話", "その打ち合わせ", "先ほどの通話", "先ほどの会話", "先ほどの打ち合わせ", 
    "さっきの通話", "さっきの会話", "さっきの打ち合わせ", "その連絡", "先ほどの連絡", "さっきの連絡", 
    "その件", "その話", "それ", "これ", "あれ", "あの通話", "あの会話", "あの打ち合わせ", 
    "あの連絡", "この通話", "この会話", "この打ち合わせ", "この連絡", "あの件", "あの話", 
    "この件", "この話"
}


