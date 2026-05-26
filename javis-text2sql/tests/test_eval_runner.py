from __future__ import annotations

import pytest

from javis_text2sql.eval.runner import evaluate_sample_fixtures
from javis_text2sql.llm.fixture import FixtureLLMClient


@pytest.mark.asyncio
async def test_evaluation_runner_covers_all_three_sample_files_and_metrics() -> None:
    report = await evaluate_sample_fixtures(llm_client=FixtureLLMClient())

    assert report["all_required_sample_files_present"]
    assert [item["file_name"] for item in report["files"]] == [
        "VJ_technologies_ja.md",
        "AJ_technologies_ja.md",
        "sumary_mau.md",
    ]
    assert report["few_shot_count"] == 15
    for category in ["topics", "entities", "amounts", "dates", "commitments", "action_items"]:
        assert category in report["aggregate_coverage"]
        assert "precision" in report["aggregate_coverage"][category]
        assert "recall" in report["aggregate_coverage"][category]
    assert report["routing"]["accuracy"] >= 0.8
    assert report["sql_validation"]["unsafe_sql_rejection_rate"] == 1.0
    assert report["text2sql_pipeline"]["expected_behavior_accuracy"] == 1.0
    assert report["text2sql_pipeline"]["retry_success_rate"] == 1.0
    assert report["performance"]["total_llm_calls"] > 0
    assert report["total_missing_facts"] == 0
