# Multi-Turn Context Manager (V1.0.0)

An advanced, high-performance system designed to manage complex multi-turn conversations for LLM-based assistants. It acts as an intelligent middleware that bridges the gap between user queries and multiple data sources (SQL, RAG, Web) while maintaining context consistency across sessions.

## 🚀 Key Features

- **2-Tier Intelligent Routing:**
  - **Tier 1 (Fast Path):** Uses Heuristics and Vector Similarity (Embeddings) for sub-20ms resolution of follow-up questions and pronouns (e.g., "he", "it", "that call").
  - **Tier 2 (Precision Path):** Leverages an LLM-based Router for complex intent detection, query rewriting, and multi-pipeline selection.
- **Advanced Context Management:**
  - **Hot/Cold Storage:** Separates lightweight metadata (Hot) from large payloads (Cold) in PostgreSQL to maximize memory efficiency.
  - **LRU Cache Eviction:** Maintains a lean footprint by keeping only the 3 most relevant topics active per session.
  - **Entity Indexing:** Automatically tracks mentioned entities (meeting IDs, dates, people) for instant pronoun resolution.
- **Resilient Execution Engines:**
  - **SQLEngine:** Translates natural language to SQL for structured data retrieval.
  - **RAGEngine:** Performs vector searches on unstructured documents using `pgvector`.
  - **WebEngine:** Simulates real-time web searches for parametric knowledge updates.
- **Hallucination Prevention:**
  - **Self-Check Verification:** Every AI response is cross-referenced against the raw retrieved context to ensure 100% factual accuracy.
- **System Stability:**
  - **Advisory Locking:** Prevents Race Conditions during concurrent cache updates in the same session.
  - **Circuit Breakers:** Automatically falls back to safe routing methods during LLM/Embedding timeouts.

## 🏗️ Technical Architecture (The 8-Step Pipeline)

1.  **Session Lock:** Acquire a PostgreSQL advisory lock to ensure sequential processing.
2.  **Metadata Fetch:** Load active session context and entity indexes.
3.  **Tiered Routing:** Decide between Tier 1 (Fast) or Tier 2 (LLM) routing.
4.  **Retrieval Execution:** Run the selected engine (SQL/RAG/Web) to fetch data.
5.  **Entity Indexing:** Update the session's entity index with new findings.
6.  **Context Update:** Upsert payloads into Hot/Cold storage and refresh LRU timers.
7.  **Answer Generation:** Generate a response using LLM or a direct template path.
8.  **Self-Check & Log:** Verify response accuracy and commit chat history.

## 📥 Input & 📤 Output

### Input Schema
| Field | Type | Description |
| :--- | :--- | :--- |
| `session_id` | `String` | Unique identifier for the user session. |
| `query` | `String` | Natural language query (can be a follow-up or brand new topic). |

### Output Schema
| Field | Type | Description |
| :--- | :--- | :--- |
| `answer` | `String` | The final synthesized response (in Japanese). |
| `metadata` | `Object` | Technical metrics: `latency_ms`, `target_pipeline`, `needs_retrieval`, `rewritten_query`, etc. |

## 🛠️ Setup & Installation

### Prerequisites
- Python 3.11+
- PostgreSQL 15+ with `pgvector` and `uuid-ossp` extensions.
- Athena LLM Gateway access.

### Installation
1.  **Clone the repository:**
    ```bash
    git clone <repo-url>
    cd multi-turn-context-manager
    ```
2.  **Setup Virtual Environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # Or .venv\Scripts\activate on Windows
    pip install -r requirements.txt
    ```
3.  **Configure Environment:**
    Create a `.env` file from the template and provide your database URL and API keys.
4.  **Initialize Database:**
    ```bash
    python scripts/init_db.py
    python scripts/init_extra_tables.py
    ```

## 🧪 Testing
The system includes a comprehensive E2E test suite covering 26 scenarios (Standard, Negative, and Recovery).

```bash
python tests/test_suite.py
```
*Current Status: 100% Pass Rate (V1.0.0).*

## 📂 Directory Structure
- `src/`: Core logic (Orchestrator, Router, Engines).
- `scripts/`: DB initialization and data migration.
- `tests/`: E2E test suite.
- `reports/`: Benchmark and technical logs.
- `docs/`: In-depth architecture and schema documentation.

---
*Developed by Gemini CLI Agent for the Javis Project.*
