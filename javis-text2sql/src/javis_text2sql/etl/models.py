from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


TurnType = Literal["decision", "question", "proposal", "complaint", "update", "small_talk"]
Sentiment = Literal["positive", "negative", "neutral"]
CommitmentStatus = Literal["pending", "done", "cancelled"]


@dataclass(frozen=True)
class Turn:
    turn_index: int
    speaker: str
    content: str
    timestamp: datetime | None = None


@dataclass(frozen=True)
class MeetingMeta:
    title: str
    meeting_date: date
    speaker_count: int
    duration_seconds: int
    summary: str | None
    user_id: str = "00000000-0000-0000-0000-000000000000"
    source_language: Literal["ja"] = "ja"


class AmountInfo(BaseModel):
    value: float = Field(default=0.0, description="Numeric value of the monetary amount")
    unit: str = Field(default="", description="Raw monetary unit such as million, man, yen")
    currency: str | None = Field(default=None, description="Normalized currency code such as VND, JPY, USD")
    context: str = Field(default="", description="Business context of the amount")

    @model_validator(mode="after")
    def resolve_currency(self) -> "AmountInfo":
        curr = (self.currency or "").strip().upper()
        if not curr:
            unit_lower = (self.unit or "").lower()
            if any(x in unit_lower for x in ["yen", "円", "man", "万", "jpy"]):
                self.currency = "JPY"
            elif any(x in unit_lower for x in ["vnd", "đồng", "dong", "đ"]):
                self.currency = "VND"
            elif any(x in unit_lower for x in ["usd", "$", "dollar"]):
                self.currency = "USD"
            else:
                self.currency = "JPY"
        else:
            self.currency = curr
        return self


class DateMention(BaseModel):
    raw_text: str = Field(default="", description="Raw date text")
    resolved_date: date | None = Field(default=None, description="Resolved ISO date when known")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Resolution confidence")


class CommitmentInfo(BaseModel):
    commitment_id: str = Field(default_factory=lambda: str(uuid4()))
    person: str = Field(default="", description="Person responsible for the commitment")
    action: str = Field(default="", description="Action to be performed")
    deadline: str | None = None
    deadline_date: date | None = None
    status: CommitmentStatus = "pending"


class PassageEnrichmentSchema(BaseModel):
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    turn_types: list[TurnType] = Field(default_factory=list)
    has_action_item: bool = False
    action_item_text: str | None = None
    has_question: bool = False
    question_text: str | None = None
    amounts: list[AmountInfo] = Field(default_factory=list)
    dates_mentioned: list[DateMention] = Field(default_factory=list)
    commitments: list[CommitmentInfo] = Field(default_factory=list)
    sentiment: Sentiment = "neutral"
    importance_score: int = Field(default=1, ge=1, le=5)

    @model_validator(mode="before")
    @classmethod
    def sanitize_turn_types(cls, data: any) -> any:
        if isinstance(data, dict):
            types = data.get("turn_types")
            if isinstance(types, list):
                sanitized = []
                for t in types:
                    if not isinstance(t, str):
                        continue
                    t_clean = t.strip().lower()
                    if t_clean in ["decision", "question", "proposal", "complaint", "update", "small_talk"]:
                        sanitized.append(t_clean)
                    elif "提案" in t_clean or "希望" in t_clean or "要請" in t_clean:
                        sanitized.append("proposal")
                    elif "質問" in t_clean or "疑問" in t_clean:
                        sanitized.append("question")
                    elif "決定" in t_clean or "合意" in t_clean or "決定事項" in t_clean:
                        sanitized.append("decision")
                    elif "不満" in t_clean or "懸念" in t_clean or "クレーム" in t_clean:
                        sanitized.append("complaint")
                    elif "雑談" in t_clean or "挨拶" in t_clean:
                        sanitized.append("small_talk")
                    elif "報告" in t_clean or "進捗" in t_clean or "更新" in t_clean:
                        sanitized.append("update")
                    else:
                        sanitized.append("update")
                data["turn_types"] = sanitized
        return data

    @model_validator(mode="after")
    def check_metadata_consistency(self) -> "PassageEnrichmentSchema":
        if self.has_action_item and not self.action_item_text:
            raise ValueError("action_item_text must be present when has_action_item=True")
        if self.has_question and not self.question_text:
            raise ValueError("question_text must be present when has_question=True")
        return self


def empty_enrichment() -> PassageEnrichmentSchema:
    return PassageEnrichmentSchema(
        topics=[],
        entities=[],
        keywords=[],
        turn_types=[],
        has_action_item=False,
        action_item_text=None,
        has_question=False,
        question_text=None,
        amounts=[],
        dates_mentioned=[],
        commitments=[],
        sentiment="neutral",
        importance_score=1,
    )
