from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Iterable

from javis_text2sql.config import SAMPLE_DATA_DIR
from javis_text2sql.etl.chunker import chunk_turns_into_passages, passage_content, split_turns
from javis_text2sql.etl.models import PassageEnrichmentSchema
from javis_text2sql.etl.samples import SAMPLE_META
from javis_text2sql.llm.client import LLMClient
from javis_text2sql.llm.fixture import FixtureLLMClient
from javis_text2sql.query.pipeline import text2sql_pipeline
from javis_text2sql.query.prompt import FEW_SHOT_EXAMPLES
from javis_text2sql.query.sql_validation import validate_sql
from javis_text2sql.routing.router import route_question

from .golden import GOLDEN_BY_FILE, GOLDEN_FIXTURES, GoldenFixture


ROUTING_GOLDEN = [
    ("総予算はいくらですか？", "sql"),
    ("未完了のコミットメントを一覧表示してください。", "sql"),
    ("山下さんは予算について何と言いましたか？", "hybrid"),
    ("この会議を要約してください。", "rag"),
    ("予算に関する金額を合計してください。", "sql"),
    ("AJ Technologiesとはどのような会社ですか？", "rag"),
]

SQL_VALIDATION_GOLDEN = [
    ("SELECT * FROM v_commitments;", True),
    ("SELECT SUM(amount_value) FROM v_amounts;", True),
    ("DELETE FROM commitments;", False),
    ("SELECT * FROM commitments;", False),
    ("SELECT * FROM v_topics; DROP TABLE meetings;", False),
]

TEXT2SQL_PIPELINE_GOLDEN = [
    {
        "question": "総予算はいくらですか？",
        "generated_sql": "SELECT SUM(amount_value) AS total_amount FROM v_amounts WHERE amount_currency = 'JPY';",
        "expected_success": True,
        "expected_data": [{"total_amount": 4500}],
        "expect_retry": False,
    },
    {
        "question": "未完了のタスクは何件ありますか？",
        "generated_sql": "SELECT COUNT(*) AS commitment_count FROM v_commitments WHERE status = 'pending';",
        "expected_success": True,
        "expected_data": [{"commitment_count": 7}],
        "expect_retry": False,
    },
    {
        "question": "unsafe",
        "generated_sql": "DROP TABLE meetings;",
        "expected_success": False,
        "expected_data": None,
        "expect_retry": False,
    },
    {
        "question": "Retry counting commitments",
        "generated_sql": "SELECT missing_column FROM v_commitments;",
        "refined_sql": "SELECT COUNT(*) AS commitment_count FROM v_commitments;",
        "expected_success": True,
        "expected_data": [{"commitment_count": 7}],
        "expect_retry": True,
        "fail_first_execution": True,
    },
]


def _norm(value: Any) -> str:
    return str(value).strip().casefold()


def _amount_key(item: dict[str, Any]) -> str:
    value = item.get("value")
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{value}|{item.get('unit')}|{item.get('currency')}|{item.get('context')}"


def _coverage(expected: Iterable[str], observed: Iterable[str]) -> dict[str, Any]:
    expected_set = {_norm(item) for item in expected}
    observed_set = {_norm(item) for item in observed}
    matched = expected_set & observed_set
    missing = expected_set - observed_set
    extra = observed_set - expected_set
    precision = len(matched) / len(observed_set) if observed_set else (1.0 if not expected_set else 0.0)
    recall = len(matched) / len(expected_set) if expected_set else 1.0
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return {
        "expected": len(expected_set),
        "observed": len(observed_set),
        "matched": len(matched),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "missing": sorted(missing),
        "extra": sorted(extra),
    }


def _fixture_to_report(fixture: GoldenFixture) -> dict[str, Any]:
    return {
        "file_name": fixture.file_name,
        "expected_topics": sorted(fixture.expected_topics),
        "expected_entities": sorted(fixture.expected_entities),
        "expected_amounts": sorted(fixture.expected_amounts),
        "expected_dates": sorted(fixture.expected_dates),
        "expected_commitments": sorted(fixture.expected_commitments),
        "expected_action_items": sorted(fixture.expected_action_items),
    }


async def _extract_file_metrics(path: Path, golden: GoldenFixture, llm_client: LLMClient) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    meta = SAMPLE_META[path.name]
    turns = split_turns(raw, reference_date=meta.meeting_date)
    chunks = chunk_turns_into_passages(turns)

    started = time.perf_counter()
    schemas: list[PassageEnrichmentSchema] = []
    for index, group in enumerate(chunks):
        schema = await llm_client.structured_output(
            system=f"Reference date: {meta.meeting_date.isoformat()}; passage={index}",
            user=passage_content(group),
            schema=PassageEnrichmentSchema,
        )
        schemas.append(schema)
    latency_ms = (time.perf_counter() - started) * 1000

    topics = {item for schema in schemas for item in schema.topics}
    entities = {item for schema in schemas for item in schema.entities}
    amounts = {_amount_key(item.model_dump(mode="json")) for schema in schemas for item in schema.amounts}
    dates = {item.raw_text for schema in schemas for item in schema.dates_mentioned}
    commitments = {item.action for schema in schemas for item in schema.commitments}
    action_text = " ".join(schema.action_item_text or "" for schema in schemas)
    action_items = {item for item in golden.expected_action_items if item in action_text}

    coverage = {
        "topics": _coverage(golden.expected_topics, topics),
        "entities": _coverage(golden.expected_entities, entities),
        "amounts": _coverage(golden.expected_amounts, amounts),
        "dates": _coverage(golden.expected_dates, dates),
        "commitments": _coverage(golden.expected_commitments, commitments),
        "action_items": _coverage(golden.expected_action_items, action_items),
    }

    missing_total = sum(len(metric["missing"]) for metric in coverage.values())
    return {
        "file_name": path.name,
        "turn_count": len(turns),
        "passage_count": len(chunks),
        "llm_calls": len(chunks),
        "latency_ms": round(latency_ms, 3),
        "coverage": coverage,
        "missing_total": missing_total,
    }


def _routing_metrics() -> dict[str, Any]:
    results = []
    correct = 0
    for question, expected in ROUTING_GOLDEN:
        decision = route_question(question)
        ok = decision.route == expected
        correct += int(ok)
        results.append({"question": question, "expected": expected, "actual": decision.route, "ok": ok})
    return {"accuracy": round(correct / len(ROUTING_GOLDEN), 4), "cases": results}


def _sql_validation_metrics() -> dict[str, Any]:
    results = []
    correct = 0
    unsafe_rejected = 0
    unsafe_total = 0
    for sql, expected_ok in SQL_VALIDATION_GOLDEN:
        validation = validate_sql(sql)
        ok = validation.ok == expected_ok
        correct += int(ok)
        if not expected_ok:
            unsafe_total += 1
            unsafe_rejected += int(not validation.ok)
        results.append(
            {
                "sql": sql,
                "expected_ok": expected_ok,
                "actual_ok": validation.ok,
                "parser": validation.parser,
                "error": validation.error,
                "ok": ok,
            }
        )
    return {
        "accuracy": round(correct / len(SQL_VALIDATION_GOLDEN), 4),
        "unsafe_sql_rejection_rate": round(unsafe_rejected / unsafe_total, 4),
        "cases": results,
    }


class _EvalTransaction:
    async def __aenter__(self) -> "_EvalTransaction":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


class _EvalAcquire:
    def __init__(self, conn: "_EvalConn") -> None:
        self.conn = conn

    async def __aenter__(self) -> "_EvalConn":
        return self.conn

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


class _EvalConn:
    def __init__(self, fail_first_execution: bool = False) -> None:
        self.fail_first_execution = fail_first_execution
        self.execution_count = 0

    def transaction(self) -> _EvalTransaction:
        return _EvalTransaction()

    async def execute(self, query: str, *args: Any) -> str:
        return "OK"

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        if "FROM entity_aliases" in query:
            return [
                {"alias": "総予算", "canonical_name": "budget"},
                {"alias": "タスク", "canonical_name": "commitment"},
            ]
        self.execution_count += 1
        if self.fail_first_execution and self.execution_count == 1:
            raise RuntimeError("column does not exist")
        if "v_amounts" in query:
            return [{"total_amount": 4500}]
        if "v_commitments" in query and "COUNT" in query.upper():
            return [{"commitment_count": 7}]
        if "v_commitments" in query:
            return [{"person": "当社", "action": "資金計画書を作成する", "status": "pending"}]
        return [{"ok": True}]


class _EvalPool:
    def __init__(self, conn: _EvalConn) -> None:
        self.conn = conn

    def acquire(self) -> _EvalAcquire:
        return _EvalAcquire(self.conn)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((percentile / 100) * (len(ordered) - 1))))
    return round(ordered[index], 3)


async def _pipeline_metrics() -> dict[str, Any]:
    cases = []
    latencies: list[float] = []
    success_count = 0
    exact_match_count = 0
    retry_expected = 0
    retry_success = 0

    for case in TEXT2SQL_PIPELINE_GOLDEN:
        client = FixtureLLMClient(
            generated_sql=[case["generated_sql"]],
            refined_sql=[case["refined_sql"]] if case.get("refined_sql") else None,
        )
        conn = _EvalConn(fail_first_execution=bool(case.get("fail_first_execution")))
        started = time.perf_counter()
        result = await text2sql_pipeline(
            case["question"],
            _EvalPool(conn),
            client,
            reference_date=SAMPLE_META["sumary_mau.md"].meeting_date,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        latencies.append(latency_ms)

        expected_success = bool(case["expected_success"])
        success_ok = result.success == expected_success
        exact_ok = result.data == case["expected_data"] if expected_success else not result.success
        retry_ok = result.retry_used == bool(case["expect_retry"])
        success_count += int(result.success)
        exact_match_count += int(exact_ok)
        if case["expect_retry"]:
            retry_expected += 1
            retry_success += int(result.success and result.retry_used)

        cases.append(
            {
                "question": case["question"],
                "success": result.success,
                "expected_success": expected_success,
                "exact_match": exact_ok,
                "retry_used": result.retry_used,
                "expected_retry": bool(case["expect_retry"]),
                "sql": result.sql,
                "error": result.error,
                "latency_ms": round(latency_ms, 3),
                "ok": success_ok and exact_ok and retry_ok,
            }
        )

    return {
        "execution_success_rate": round(success_count / len(TEXT2SQL_PIPELINE_GOLDEN), 4),
        "expected_behavior_accuracy": round(sum(int(case["ok"]) for case in cases) / len(cases), 4),
        "exact_result_match_rate": round(exact_match_count / len(cases), 4),
        "EX_rate": round(success_count / len(TEXT2SQL_PIPELINE_GOLDEN), 4),
        "VES_rate": round(exact_match_count / len(cases), 4),
        "retry_success_rate": round(retry_success / retry_expected, 4) if retry_expected else 1.0,
        "latency_ms_p50": _percentile(latencies, 50),
        "latency_ms_p95": _percentile(latencies, 95),
        "cases": cases,
    }


async def evaluate_sample_fixtures(
    sample_dir: Path = SAMPLE_DATA_DIR,
    llm_client: LLMClient | None = None,
) -> dict[str, Any]:
    client = llm_client or FixtureLLMClient()
    file_reports = []
    for golden in GOLDEN_FIXTURES:
        path = sample_dir / golden.file_name
        if not path.exists():
            raise FileNotFoundError(f"Required sample fixture is missing: {path}")
        file_reports.append(await _extract_file_metrics(path, golden, client))

    coverage_categories = ["topics", "entities", "amounts", "dates", "commitments", "action_items"]
    aggregate: dict[str, Any] = {}
    for category in coverage_categories:
        expected = sum(report["coverage"][category]["expected"] for report in file_reports)
        matched = sum(report["coverage"][category]["matched"] for report in file_reports)
        observed = sum(report["coverage"][category]["observed"] for report in file_reports)
        precision = matched / observed if observed else (1.0 if expected == 0 else 0.0)
        recall = matched / expected if expected else 1.0
        aggregate[category] = {
            "expected": expected,
            "observed": observed,
            "matched": matched,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
        }

    total_missing = sum(report["missing_total"] for report in file_reports)
    ingestion_latencies = [report["latency_ms"] for report in file_reports]
    return {
        "sample_files": [_fixture_to_report(fixture) for fixture in GOLDEN_FIXTURES],
        "files": file_reports,
        "aggregate_coverage": aggregate,
        "performance": {
            "ingestion_latency_ms_p50": _percentile(ingestion_latencies, 50),
            "ingestion_latency_ms_p95": _percentile(ingestion_latencies, 95),
            "total_llm_calls": sum(report["llm_calls"] for report in file_reports),
            "total_passages": sum(report["passage_count"] for report in file_reports),
        },
        "routing": _routing_metrics(),
        "sql_validation": _sql_validation_metrics(),
        "text2sql_pipeline": await _pipeline_metrics(),
        "few_shot_count": len(FEW_SHOT_EXAMPLES),
        "all_required_sample_files_present": set(GOLDEN_BY_FILE) == {report["file_name"] for report in file_reports},
        "total_missing_facts": total_missing,
        "status": "pass" if total_missing == 0 else "fail",
    }


def write_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=list), encoding="utf-8")


def evaluate_sync(sample_dir: Path = SAMPLE_DATA_DIR) -> dict[str, Any]:
    return asyncio.run(evaluate_sample_fixtures(sample_dir=sample_dir))
