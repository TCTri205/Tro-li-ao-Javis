from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime

class Entity(BaseModel):
    id: str
    type: str  # e.g., "meeting", "person", "topic", "document"
    name: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0

class CachedResult(BaseModel):
    query: str
    result_type: Literal["rag", "sql", "web"]
    data: Any
    timestamp: datetime = Field(default_factory=datetime.now)

class DetectorOutput(BaseModel):
    is_followup: bool = Field(default=False, description="Whether the current query is a follow-up to previous turns.")
    confidence: float = Field(default=0.0, description="Confidence score from 0.0 to 1.0")
    relation_type: str = Field(default="none", description="One of: same_entity, same_document, same_subject_new_param, topic_shift, clarification, none")
    referenced_entities: List[str] = Field(default_factory=list, description="List of entity IDs or names referenced in this query (e.g., 'meeting_20260608', 'Ông ấy').")
    needs_retrieval: Literal["none", "partial", "full"] = Field(default="none", description="Whether new retrieval is needed.")
    rewritten_standalone_query: str = Field(default="", description="A rewritten query that can stand alone without context. MUST maintain original language.")
    search_keyword: Optional[str] = Field(default=None, description="If intent_category is 'web', extract ONLY the most important search keywords (e.g. 'Three Luster株式会社'). Otherwise null.")
    intent_category: Literal["sql", "rag", "web", "pure_llm"] = Field(default="pure_llm", description="The type of retrieval or engine to route to.")

class TurnState(BaseModel):
    # LangGraph state representation
    session_id: str
    messages: List[Dict[str, str]]  # list of {"role": "...", "content": "..."}
    current_query: str
    detector_output: Optional[DetectorOutput] = None
    active_entities: List[Entity] = Field(default_factory=list)
    retrieval_plan: Optional[str] = None
    retrieved_data: Optional[Any] = None
    final_answer: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
