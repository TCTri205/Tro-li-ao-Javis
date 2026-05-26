from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel

from javis_text2sql.etl.models import PassageEnrichmentSchema


def _base() -> dict[str, Any]:
    return {
        "topics": [],
        "entities": [],
        "keywords": [],
        "turn_types": [],
        "has_action_item": False,
        "action_item_text": None,
        "has_question": False,
        "question_text": None,
        "amounts": [],
        "dates_mentioned": [],
        "commitments": [],
        "sentiment": "neutral",
        "importance_score": 1,
    }


def _append_unique(target: list[Any], value: Any) -> None:
    if value not in target:
        target.append(value)


def fixture_enrichment_for_text(text: str) -> dict[str, Any]:
    data = _base()

    if "VJ Technologies" in text or "VJ TECHNOLOGIES" in text or "VJ Technologies有限会社" in text:
        for item in ["AI", "Microservices", "Machine learning", "DX solutions"]:
            _append_unique(data["topics"], item)
        for item in ["VJ Technologies", "ASSET JAPAN", "Đà Nẵng", "Quang Hữu Hiếu"]:
            _append_unique(data["entities"], item)
        for item in ["AI", "Microservices", "Machine learning"]:
            _append_unique(data["keywords"], item)
        data["importance_score"] = 4

    for product in ["DX-ASAP", "Energy Japan", "GoEMON Jobs", "GoEMON Home", "GoEMON Community"]:
        if product in text:
            _append_unique(data["entities"], product)
            _append_unique(data["topics"], product)
            _append_unique(data["keywords"], product)
            data["importance_score"] = max(data["importance_score"], 4)

    if "AJ Technologies" in text or "株式会社AJテクノロジーズ" in text or "AJテクノロジーズ" in text:
        for item in ["AI platform", "financial services", "real estate", "housing loan"]:
            _append_unique(data["topics"], item)
        for item in ["AJ Technologies", "Yoshio Yamashita", "VJ Technologies", "ONE Financial Service"]:
            if item in text or item in {"AJ Technologies", "Yoshio Yamashita"}:
                _append_unique(data["entities"], item)
        data["importance_score"] = 4

    feature_markers = {
        "ラクかりex": "ラクかりex",
        "ホムすん": "ホムすん",
        "AI OCR": "AI OCR",
        "AI-OCR": "AI OCR",
        "AIチャットボット": "AIチャットボット",
        "音声認識＆議事録作成": "音声認識＆議事録作成",
        "施工進捗管理": "施工進捗管理",
        "住宅ローン分析・提案": "住宅ローン分析・提案",
    }
    for marker, entity in feature_markers.items():
        if marker in text:
            _append_unique(data["entities"], entity)
            _append_unique(data["keywords"], entity)
            data["importance_score"] = max(data["importance_score"], 4)

    if "４,５００万円" in text or "4,500万円" in text or "４５００万円" in text:
        _append_unique(data["topics"], "budget")
        _append_unique(data["entities"], "4,500万円")
        _append_unique(
            data["amounts"],
            {"value": 4500, "unit": "万円", "currency": "JPY", "context": "総予算"},
        )
        data["importance_score"] = 5

    if "５月３０日" in text or "5月30日" in text:
        _append_unique(
            data["dates_mentioned"],
            {"raw_text": "５月３０日（土）１０:００", "resolved_date": None, "confidence": 0.8},
        )
        _append_unique(data["topics"], "next meeting")
        data["importance_score"] = 5

    commitment_rules = [
        ("土地を３〜４件選定", "当社", "総額4,500万円内に収まりそうな土地を3〜4件選定してメール送付する", "今週金曜"),
        ("土地を３〜４か所選定", "当社", "総額4,500万円内に収まりそうな土地を3〜4か所選定してメール送付する", "今週金曜"),
        ("キッチン画像３〜４枚", "来訪者", "好みのキッチン画像3〜4枚を公式LINEへ送付する", "今週日曜"),
        ("ハザードマップ", "当社", "最新の土地相場とハザードマップ資料を用意する", "モデルハウス案内前"),
        ("建築実例パンフレット", "当社", "吹き抜けのあるリビングの建築実例パンフレットを郵送する", "明日中"),
        ("資金計画書", "当社", "資金計画書を作成する", "次回打ち合わせまで"),
        ("家賃・電気・ガス", "来訪者", "家賃・電気・ガスの明細を次回に提示する", "次回"),
        ("夫に確認", "来訪者", "夫に確認し次回参加を確保する", "次回"),
    ]
    for marker, person, action, deadline in commitment_rules:
        if marker in text:
            _append_unique(
                data["commitments"],
                {
                    "person": person,
                    "action": action,
                    "deadline": deadline,
                    "deadline_date": None,
                    "status": "pending",
                },
            )

    if data["commitments"]:
        data["has_action_item"] = True
        data["action_item_text"] = "; ".join(item["action"] for item in data["commitments"])
        _append_unique(data["turn_types"], "update")
        _append_unique(data["turn_types"], "proposal")
        data["importance_score"] = 5

    if "懸念" in text or "課題" in text:
        _append_unique(data["turn_types"], "complaint")
        data["sentiment"] = "negative"
    elif data["topics"] or data["entities"]:
        data["sentiment"] = "neutral"

    return data


class FixtureLLMClient:
    """Deterministic LLM adapter for tests and offline sample ingestion."""

    def __init__(self, generated_sql: list[str] | None = None, refined_sql: list[str] | None = None) -> None:
        self.generated_sql = generated_sql or []
        self.refined_sql = refined_sql or []
        self.generate_calls: list[tuple[str, str]] = []

    async def structured_output(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        data = fixture_enrichment_for_text(user)
        if schema is PassageEnrichmentSchema:
            return PassageEnrichmentSchema(**deepcopy(data))
        return schema(**deepcopy(data))

    async def generate(self, system: str, user: str) -> str:
        self.generate_calls.append((system, user))
        lower = system.lower()
        if "fix the sql" in lower or "refine" in lower:
            if self.refined_sql:
                return self.refined_sql.pop(0)
        if self.generated_sql:
            return self.generated_sql.pop(0)
        if "commitment" in user.lower() or "cam kết" in user.lower() or "タスク" in user:
            return "SELECT person, action, deadline, status FROM v_commitments WHERE status = 'pending';"
        if "budget" in user.lower() or "ngân sách" in user.lower() or "予算" in user:
            return "SELECT SUM(amount_value) AS total_amount FROM v_amounts WHERE amount_currency = 'JPY';"
        return "SELECT meeting_title, topic FROM v_topics LIMIT 20;"
