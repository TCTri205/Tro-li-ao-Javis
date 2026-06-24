from typing import List, Dict, Any, Optional
from .models import Entity, TurnState
from .context_graph import ContextGraph
from .llm_client import LLMClient

class ContextMemoryManager:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
        self.graph = ContextGraph()
        # In a real app, this would be Redis/DB keyed by session_id
        self.sessions: Dict[str, TurnState] = {}

    def get_state(self, session_id: str) -> TurnState:
        if session_id not in self.sessions:
            self.sessions[session_id] = TurnState(session_id=session_id, messages=[], current_query="")
        return self.sessions[session_id]

    def save_state(self, state: TurnState):
        self.sessions[state.session_id] = state

    def update_context(self, state: TurnState, detector_output: Any) -> TurnState:
        # Extract new entities from the rewritten query if it's not a pure follow-up
        # For simplicity, we assume the planner/generator will add concrete entities (like Meeting IDs)
        # Here we just resolve coreferences if needed.
        state.detector_output = detector_output
        
        # If it's a follow-up, try to ensure active entities are correctly prioritized
        if detector_output.is_followup:
            for ref in detector_output.referenced_entities:
                # E.g. ref could be "meeting_20260608"
                # If it's already an active entity, we keep it active.
                # If it's a pronoun, resolve it using the graph
                active_id = state.active_entities[0].id if state.active_entities else None
                resolved_id = self.graph.resolve_coreference(ref, active_id)
                if resolved_id:
                    # Bring resolved entity to front
                    state.active_entities = [e for e in state.active_entities if e.id != resolved_id]
                    entity_data = self.graph.get_entity(resolved_id)
                    if entity_data:
                        state.active_entities.insert(0, Entity(id=resolved_id, type=entity_data['type'], name=entity_data.get('name'), attributes=entity_data))
        
        return state

    def add_to_history(self, session_id: str, role: str, content: str):
        state = self.get_state(session_id)
        state.messages.append({"role": role, "content": content})
        self.save_state(state)

    def register_entity(self, state: TurnState, entity: Entity):
        self.graph.add_entity(entity)
        # Add to active entities if not present
        if not any(e.id == entity.id for e in state.active_entities):
            state.active_entities.insert(0, entity)
        self.save_state(state)
