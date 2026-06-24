from typing import Any
from .models import TurnState
from .llm_client import LLMClient

class AnswerGenerator:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
        self.system_prompt = """あなたは親切で知的なアシスタントです。
ユーザーの最新の質問、会話履歴、およびシステムから取得したデータが提供されます。
あなたの仕事は、提供されたコンテキストに基づいて、ユーザーの質問に自然な日本語で答えることです。

【重要 - 検証とファクトチェック (Verification Step)】
- 提供された「取得されたデータ (Retrieved Data)」に厳密に基づいて回答してください。
- データを捏造したり、推測で数値を答えたりしないでください。
- 外部データベースやRAGから取得した具体的な情報（例: 会議の長さ、発言回数、企業情報）を使用する場合は、回答に含めてください。
- 必要がない限り、「キャッシュを見ました」や「データベースを検索しました」といったシステム内部の動作については明言しないでください。
- 丁寧な言葉遣い（敬語）を使用してください。

取得されたデータ:
{retrieved_data}

会話履歴:
{history}
"""

    def generate(self, state: TurnState) -> TurnState:
        history_str = ""
        for msg in state.messages[-5:]:
            history_str += f"{msg['role'].capitalize()}: {msg['content']}\n"
            
        retrieved_data_str = str(state.retrieved_data) if state.retrieved_data else "情報なし"
        
        system = self.system_prompt.format(retrieved_data=retrieved_data_str, history=history_str)
        user = f"ユーザーの質問: {state.current_query}\n上記を踏まえて回答を作成してください。"
        
        answer = self.llm_client.generate_text(system_prompt=system, user_prompt=user)
        state.final_answer = answer
        
        return state
