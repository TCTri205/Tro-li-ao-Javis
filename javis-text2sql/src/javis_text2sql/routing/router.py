from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal


Route = Literal["sql", "rag", "hybrid"]
SqlIntent = Literal["aggregate", "filter", "list", "status_check", "date_filter", "commitment", "amount"]


class RoutingDecision(BaseModel):
    route: Route
    confidence: float = Field(ge=0.0, le=1.0)
    sql_intent: SqlIntent | None = None
    requires_numeric: bool


SQL_INTENTS: dict[SqlIntent, list[str]] = {
    "aggregate": ["いくつ", "合計", "何件", "count", "sum"],
    "filter": ["条件", "filter", "where"],
    "list": ["一覧", "リスト", "list"],
    "status_check": ["完了", "未完了", "pending", "done"],
    "date_filter": ["期限", "日付", "今週", "先月", "deadline"],
    "commitment": ["タスク", "約束", "宿題", "action item"],
    "amount": ["予算", "金額", "万円", "budget", "価格", "費用"],
}

RAG_SIGNALS = [
    "要約",
    "なぜ",
    "意見",
    "説明",
    "概要",
    "summary",
    "何と",
    "どうして",
    "決定",
    "決議",
    "決",
]

NUMERIC_SIGNALS = [
    "何件",
    "合計",
    "いくら",
    "金額",
    "予算",
    "万円",
    "count",
    "sum",
    "価格",
    "費用",
]


def _find_sql_intents(question_lower: str) -> list[SqlIntent]:
    intents: list[SqlIntent] = []
    for intent, signals in SQL_INTENTS.items():
        if any(signal.lower() in question_lower for signal in signals):
            intents.append(intent)
    return intents


def route_question(question: str) -> RoutingDecision:
    question_lower = question.lower()
    sql_intents = _find_sql_intents(question_lower)
    has_rag_signal = any(signal.lower() in question_lower for signal in RAG_SIGNALS)
    requires_numeric = any(signal.lower() in question_lower for signal in NUMERIC_SIGNALS)

    if sql_intents and has_rag_signal:
        return RoutingDecision(
            route="hybrid",
            confidence=0.82,
            sql_intent=sql_intents[0],
            requires_numeric=requires_numeric,
        )
    if sql_intents:
        return RoutingDecision(
            route="sql",
            confidence=0.9 if requires_numeric else 0.78,
            sql_intent=sql_intents[0],
            requires_numeric=requires_numeric,
        )
    return RoutingDecision(route="rag", confidence=0.74 if has_rag_signal else 0.62, requires_numeric=False)
