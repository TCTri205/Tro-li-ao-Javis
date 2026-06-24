from typing import Dict, Any, TypedDict
from langgraph.graph import StateGraph, END
from .models import TurnState, Entity
from .llm_client import LLMClient
from .layer1_detector import FollowUpDetector
from .layer2_memory import ContextMemoryManager
from .cache_manager import CacheManager
from .layer3_planner import RetrievalPlanner
from .layer4_generator import AnswerGenerator
from .rag_engine import RAGEngine
from .web_engine import WebEngine

class HCACIS:
    def __init__(self, detector_llm: LLMClient, generator_llm: LLMClient, db_pool: Any):
        self.detector_llm = detector_llm
        self.generator_llm = generator_llm
        
        self.detector = FollowUpDetector(detector_llm)
        self.memory_manager = ContextMemoryManager(detector_llm)
        self.cache_manager = CacheManager()
        
        self.rag_engine = RAGEngine()
        self.web_engine = WebEngine()
        
        # Planner still uses detector_llm internally for minor decisions if needed
        self.planner = RetrievalPlanner(self.cache_manager, detector_llm, db_pool, self.rag_engine, self.web_engine)
        self.generator = AnswerGenerator(generator_llm)
        
        self.app = self._build_graph()

    def _build_graph(self):
        class GraphState(TypedDict):
            session_id: str
            current_query: str
            turn_state: TurnState

        def detect_node(state: GraphState):
            turn_state = state["turn_state"]
            acti
            return {"turn_state": turn_state}

        async def plan_node(state: GraphState):
            turn_state = state["turn_state"]
            turn_state = await self.planner.execute_plan(turn_state)
            return {"turn_state": turn_state}

        def generate_node(state: GraphState):
            turn_state = state["turn_state"]
            turn_state = self.generator.generate(turn_state)
            
            # Post generation: Add to history
            self.memory_manager.add_to_history(state["session_id"], "user", state["current_query"])
            self.memory_manager.add_to_history(state["session_id"], "assistant", turn_state.final_answer)
            return {"turn_state": turn_state}

        workflow = StateGraph(GraphState)
        
        workflow.add_node("detector", detect_node)
        workflow.add_node("planner", plan_node)
        workflow.add_node("generator", generate_node)
        
        workflow.set_entry_point("detector")
        workflow.add_edge("detector", "planner")
        workflow.add_edge("planner", "generator")
        workflow.add_edge("generator", END)
        
        return workflow.compile()

    async def process_query(self, session_id: str, query: str) -> str:
        turn_state = self.memory_manager.get_state(session_id)
        turn_state.current_query = query
        
        initial_state = {
            "session_id": session_id,
            "current_query": query,
            "turn_state": turn_state
        }
        
        result = await self.app.ainvoke(initial_state)
        
        final_turn_state = result["turn_state"]
        self.memory_manager.save_state(final_turn_state)
        
        return final_turn_state.final_answer
