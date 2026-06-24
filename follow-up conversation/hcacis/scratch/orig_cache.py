from typing import Dict, Any, Optional, List
from .models import CachedResult

class CacheManager:
    def __init__(self):
        # L1 Cache: In-memory dictionary
        # Key: "rag_{entity_id}", "sql_{entity_id}", etc.
        self.l1_cache: Dict[str, CachedResult] = {}
        # We could add L2 (Redis) and L3 (ChromaDB) here

    def set_cache(self, key: str, result_type: str, data: Any, query: str):
        self.l1_cache[key] = CachedResult(query=query, result_type=result_type, data=data)

    def get_cache(self, key: str) -> Optional[CachedResult]:
        return self.l1_cache.get(key)

    def search_semantic_cache(self, query: str) -> Optional[CachedResult]:
        # Mock semantic search using exact match for now
        # In production, use ChromaDB or FAISS to embed the query and find nearest neighbor
        for result in self.l1_cache.values():
            if result.query == query:
                return result
        return None
