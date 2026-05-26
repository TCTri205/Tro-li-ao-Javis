from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GoldenFixture:
    file_name: str
    expected_topics: set[str] = field(default_factory=set)
    expected_entities: set[str] = field(default_factory=set)
    expected_amounts: set[str] = field(default_factory=set)
    expected_dates: set[str] = field(default_factory=set)
    expected_commitments: set[str] = field(default_factory=set)
    expected_action_items: set[str] = field(default_factory=set)


GOLDEN_FIXTURES = [
    GoldenFixture(
        file_name="VJ_technologies_ja.md",
        expected_topics={"AI", "Microservices", "Machine learning", "DX-ASAP", "Energy Japan"},
        expected_entities={
            "VJ Technologies",
            "ASSET JAPAN",
            "Đà Nẵng",
            "Quang Hữu Hiếu",
            "DX-ASAP",
            "Energy Japan",
            "GoEMON Jobs",
            "GoEMON Home",
            "GoEMON Community",
        },
    ),
    GoldenFixture(
        file_name="AJ_technologies_ja.md",
        expected_topics={"AI platform", "financial services", "real estate", "housing loan"},
        expected_entities={
            "AJ Technologies",
            "Yoshio Yamashita",
            "VJ Technologies",
            "ONE Financial Service",
            "ラクかりex",
            "ホムすん",
            "AI OCR",
            "AIチャットボット",
            "音声認識＆議事録作成",
            "施工進捗管理",
            "住宅ローン分析・提案",
        },
    ),
    GoldenFixture(
        file_name="sumary_mau.md",
        expected_topics={"budget", "next meeting"},
        expected_entities={"4,500万円"},
        expected_amounts={"4500|万円|JPY|総予算"},
        expected_dates={"５月３０日（土）１０:００"},
        expected_commitments={
            "総額4,500万円内に収まりそうな土地を3〜4件選定してメール送付する",
            "好みのキッチン画像3〜4枚を公式LINEへ送付する",
            "最新の土地相場とハザードマップ資料を用意する",
            "吹き抜けのあるリビングの建築実例パンフレットを郵送する",
            "資金計画書を作成する",
            "家賃・電気・ガスの明細を次回に提示する",
            "夫に確認し次回参加を確保する",
        },
        expected_action_items={
            "総額4,500万円内に収まりそうな土地",
            "キッチン画像",
            "ハザードマップ",
            "建築実例パンフレット",
            "資金計画書",
            "家賃・電気・ガス",
            "夫に確認",
        },
    ),
]

GOLDEN_BY_FILE = {fixture.file_name: fixture for fixture in GOLDEN_FIXTURES}
