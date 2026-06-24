import re
from typing import List, Dict, Any
from .models import DetectorOutput
from .llm_client import LLMClient

class FollowUpDetector:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
        self.system_prompt = """あなたは会話コンテキストを理解し、ルーターとして機能する高度なAIアシスタントです。
最新のユーザーの質問、直近の会話履歴、およびアクティブなエンティティ（現在話題になっている対象）を与えられます。
タスク：現在の質問が以前の会話のフォローアップ（続き）であるかどうかを判断し、関係性を特定し、質問が単独で意味を成すように書き直し、使用すべきエンジン（intent_category）を決定してください。

利用可能なアクティブコンテキスト:
{active_context}

直近の履歴:
{history}

# 'needs_retrieval' のルール:
- "none": 答えが既にアクティブコンテキストや履歴に含まれている場合。
- "partial": 既存のエンティティに関する新しい側面を尋ねるが、部分的な検索で対応できる場合。
- "full": 新しい情報や完全に新しいトピックを検索する必要がある場合。

# 'intent_category' のルール:
- "sql": 定量的なデータ、時間、回数、誰が何回話したか、リスト、最長/最短など。特定のキーワードや名前が何回言及されたかを数える質問も含まれます。
- "rag": 会議の「内容」、「議論されたトピック」、「何を話したか」などテキスト検索。
- "web": インターネットで調べるべき一般知識や企業情報など。
- "pure_llm": 挨拶、要約、翻訳など外部検索が不要な質問。

# 'rewritten_standalone_query' と 'search_keyword' の厳密なルール:
- 質問を書き直す際は、元の言語（日本語なら日本語）を維持し、絶対に存在しない単語や無意味な文字列（Hallucination）を生成しないでください。
- intent_category が "web" の場合のみ、検索エンジンに入力するための最も短いキーワード（企業名など）を 'search_keyword' に抽出してください。
- IMPORTANT: JSON出力の際、日本語テキストや記号（?など）に Unicodeエスケープシーケンス（例: \u6628）を絶対に使用しないでください。生の文字（Raw characters）をそのまま出力してください。

# 'relation_type' のルール:
- "same_entity": 同じ会議、人物に言及。
- "same_document": 同じドキュメント内での特定。
- "topic_shift": 新しいトピック。
- "clarification": 前の回答の説明を求める場合。
- "none": フォローアップではない。

# Few-Shot Examples (Reference):
User: "今月の会議で最も長かったものはどれですか？" -> intent_category="sql", needs_retrieval="full", is_followup=False
User (Follow-up): "その通話ではどんな内容が話されていましたか？" -> intent_category="rag", needs_retrieval="partial", is_followup=True, relation_type="same_entity", rewritten_standalone_query="今月の最も長かった会議ではどんな内容が話されていましたか？"
User (Follow-up): "その電話の中で、梅田さんについては何回言及されていますか？" -> intent_category="sql", needs_retrieval="partial", is_followup=True, relation_type="same_entity", rewritten_standalone_query="今月の最も長かった会議の中で、梅田さんについては何回言及されていますか？"
User: "Three Luster株式会社について調べて。" -> intent_category="web", needs_retrieval="full", is_followup=False, search_keyword="Three Luster株式会社"
User: "今の説明を要約して。" -> intent_category="pure_llm", needs_retrieval="none", is_followup=True
"""

    def _rule_based_pronoun_check(self, query: str) -> bool:
        """
        Rule-based fallback: Quickly check if the query contains Japanese/Vietnamese pronouns
        that highly indicate a follow-up.
        """
        pronouns = [r"その", r"あの", r"この", r"彼", r"彼女", r"そこ", r"それ", r"nó", r"ấy", r"đó", r"ông ấy", r"bà ấy"]
        pattern = "|".join(pronouns)
        if re.search(pattern, query, re.IGNORECASE):
            return True
        return False

    async def detect(self, current_query: str, history: List[Dict[str, str]], active_context: Dict[str, Any]) -> DetectorOutput:
        history_str = ""
        for msg in history[-5:]:
            history_str += f"{msg['role'].capitalize()}: {msg['content']}\n"
        
        context_str = str(active_context)

        # Rule-based hint
        has_pronoun = self._rule_based_pronoun_check(current_query)
        hint = "\n[SYSTEM HINT]: 質問に代名詞が含まれているため、フォローアップの可能性が高いです。" if has_pronoun else ""

        system = self.system_prompt.format(active_context=context_str, history=history_str)
        user = f"現在のユーザーの質問: {current_query}{hint}\n\nこの質問を分析し、JSONスキーマを出力してください。"

        return await self.llm_client.structured_output(system_prompt=system, user_prompt=user, schema=DetectorOutput)
