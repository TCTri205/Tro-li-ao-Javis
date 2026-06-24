import sys
import os
from datetime import date
from typing import Any

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from numeric_sql_tool_v2.src.numeric_sql_tool.pipeline import run_numeric_pipeline
from numeric_sql_tool_v2.src.numeric_sql_tool.models import NumericResult

from .models import TurnState, Entity
from .cache_manager import CacheManager
from .llm_client import LLMClient
from .rag_engine import RAGEngine
from .web_engine import WebEngine

class RetrievalPlanner:
    def __init__(self, cache_manager: CacheManager, llm_client: LLMClient, db_pool: Any, rag_engine: RAGEngine, web_engine: WebEngine):
        self.cache = cache_manager
        self.llm_client = llm_client
        self.db_pool = db_pool
        self.rag_engine = rag_engine
        self.web_engine = web_engine
        
        self.default_user_id = "00000000-0000-0000-0000-000000000001"
        self.default_reference_date = date(2026, 5, 1)

    async def execute_plan(self, state: TurnState) -> TurnState:
        detector = state.detector_output
        query = detector.rewritten_standalone_query if detector and detector.rewritten_standalone_query else state.current_query
        needs_retrieval = detector.needs_retrieval if detector else "full"
        intent_category = detector.intent_category if detector else "pure_llm"
        
        state.retrieval_plan = f"{needs_retrieval} ({intent_category})"

        # 1. PURE LLM or NO RETRIEVAL
        if inte
                        transcript_filter = ent.attributes["transcript_id"]
                        break
            
            docs = self.rag_engine.search_transcript(query, transcript_id_filter=transcript_filter)
            state.retrieved_data = {"source": "RAG", "docs": docs}
            self.cache.set_cache(f"rag_{hash(query)}", "rag", state.retrieved_data, query)
            return state

        # 4. SQL (Numeric Pipeline)
        if intent_category == "sql":
            try:
                result: NumericResult = await run_numeric_pipeline(
                    question=query,
                    db_pool=self.db_pool,
                    llm_client=None, # Use the robust heuristic/LLM within the pipeline
                    user_id=self.default_user_id,
                    reference_date=self.default_reference_date
                )
                state.retrieved_data = result.model_dump()
                
                # Register SQL Result Entity and extract transcript_id if available
                entity_attrs = {}
                if result.rows and len(result.rows) > 0:
                    metadata = result.rows[0].metadata
                    if metadata and "transcript_id" in metadata:
                        entity_attrs["transcript_id"] = metadata["transcript_id"]

                entity_id = "sql_result_" + str(hash(query))
                self.cache.set_cache(f"sql_{entity_id}", "sql", state.retrieved_data, query)
                state.active_entities.insert(0, Entity(id=entity_id, type="sql_result", name="Query Result", attributes=entity_attrs))
                
            except Exception as e:
                state.retrieved_data = f"SQLデータベース検索中にエラーが発生しました: {e}"
            return state

        return state
