# MULTI-TURN CONTEXT MANAGER V2 - BENCHMARK REPORT

**Date:** 2026-06-17
**Version:** 2.0.0
**Status:** SUCCESS (95.45% Pass Rate)

## 1. Executive Summary
The V2 test suite represents a significant expansion in scenario complexity, moving from basic multi-turn logic to advanced reasoning, cross-document analysis, and strict hallucination control. Following an initial failure rate of 18.18%, a series of architectural refinements were implemented across the retrieval engines and orchestrator. The final system achieved a **95.45% pass rate**, demonstrating high reliability in resolving ambiguous pronouns and handling complex cross-session reasoning.

## 2. KPI Metrics
| Metric | Value |
| :--- | :--- |
| **Total Test Cases Run** | 22 |
| **Passed Test Cases** | 21 (95.45%) |
| **Failed Test Cases** | 1 (4.55%) |
| **Average Latency** | 11721.86ms |
| **p95 Latency** | 41967.46ms |
| **p99 Latency** | 41967.46ms |
| **Cache Hit Rate (none)** | 18.18% (4 slots) |
| **Cache Partial Hit Rate** | 9.09% (2 slots) |
| **Self-Check Pass Rate** | 94.44% |

## 3. Comparison with V1
| Feature | V1 (Baseline) | V2 (Current) | Evolution |
| :--- | :--- | :--- | :--- |
| **Scenario Depth** | Basic pronoun follow-up. | Cross-document reasoning & switchbacks. | **Advanced Reasoning** |
| **RAG Strategy** | Top-K similarity only. | Balanced Fair-Sampling across docs. | **Bias Reduction** |
| **Entity Memory** | Topic-key matching. | Persistent `summary_context` in prompt. | **Zero-forgetting** |
| **Query Rewriting** | Simple substitution. | LLM-driven multi-entity resolution. | **Higher Precision** |
| **Robustness** | Basic error handling. | Circuit Breakers & Strict Extraction. | **Production Ready** |

## 4. Fixes & Improvements in V2
- **Balanced RAG Retrieval:** Implemented a "Fair Sampling" algorithm in `RAGEngine` that ensures chunks are retrieved from ALL target documents. This fixed failures in cross-document reasoning (e.g., comparing GT_06, GT_07, and GT_08).
- **Persistent Short-term Memory:** The `IntelligentOrchestrator` now passes `summary_context` (metadata about the current topic) into the final LLM prompt. This solved the "Switchback" bug where the model would forget names of entities discussed 2-3 turns ago.
- **Strict Entity Extraction:** Modified `EntityExtractor` to block the indexing of generic terms like "情報" (info), "データ" (data), or "詳細" (details). This prevented Tier 1 from making false-positive matches on ambiguous queries.
- **Advanced Query Rewriting:** Enhanced the LLM Router's prompt to prioritize resolving "They", "She", or "The representative" into specific proper nouns based on recent chat history.

## 5. Detailed Test Results
| Category | Test ID | Status | Notes |
| :--- | :--- | :--- | :--- |
| **Standard** | STD_TURN_4_SWITCHBACK | ✅ PASS | Successfully identified Yokobori-san after topic switching. |
| **Advanced** | CROSS_DOC_REASONING | ✅ PASS | Corrected identification of 'AJ Technologies' across 3 docs. |
| **Entity** | ENTITY_COMPARISON | ❌ FAIL | Model remains too cautious to confirm 'different purposes' without explicit text. |
| **NEG** | NEG_016_SQL_FAILURE | ✅ PASS | Fallback logic correctly handled schema-mismatch queries. |
| **Stress** | CONCURRENT_5_REQS | ✅ PASS | Handled 5 parallel requests with consistent routing. |

## 6. Remaining Edge Cases
- **Subjective Comparison:** Queries like "Did they call for the same purpose?" sometimes fail if the RAG context doesn't contain a literal statement of similarity/difference, even if it's obvious to a human reader.

## 7. Technical Environment
- **LLM:** Javis-Qwen (via Athena Gateway)
- **Database:** PostgreSQL 15 (pgvector)
- **Engine:** 8-Step Multi-turn Pipeline
- **Orchestration:** Sequential Locking + 2-Tier Routing

---
*Report generated automatically by Gemini CLI Agent.*
