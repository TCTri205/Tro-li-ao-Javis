import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import redis
import chromadb
from langchain_ollama import OllamaEmbeddings
from .models import CachedResult

logger = logging.getLogger(__name__)

class CacheManager:
    def __init__(self):
        # L1 Cache: In-memory dictionary
        self.l1_cache: Dict[str, CachedResult] = {}
        
        # L2 Cache: Redis (TTL: 1 hour)
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        try:
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
            self.redis_client.ping()
            self.redis_connected = True
        except Exception as e:
            logger.error(f"Failed to connect to Redis. Running without L2 Cache. Error: {e}")
            self.redis_connected = False
            self.redis_client = None

        # L3 Cache: Semantic Cache (ChromaDB)
        persist_directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
        try:
            self.chroma_client = chromadb.PersistentClient(path=persist_directory)
            self.embeddings = OllamaEmbeddings(model="nomic-embed-text")
            self.semantic_collection = self.chroma_client.get_or_create_collection(name="semantic_cache")
            self.chroma_connected = True
        except Exception as e:
            logger.error(f"Failed to connect to ChromaDB for Semantic Cache. Error: {e}")
            self.chroma_connected = False

    def set_cache(self, key: str, result_type: str, data: Any, query: str):
        cached_result = CachedResult(query=query, result_type=result_type, data=data)
        
        # 1. Set L1
        self.l1_cache[key] = cached_result
        
        # 2. Set L2 (Redis) with 3600 seconds TTL
        if self.redis_connected:
            try:
                # Convert pydantic to dict then json string
                json_data = cached_result.model_dump_json()
                self.redis_client.setex(key, 3600, json_data)
            except Exception as e:
                logger.error(f"Failed to set L2 Cache: {e}")

        # 3. Set L3 (Semantic Cache)
        if self.chroma_connected:
            try:
                # Store the query as the document, and data stringified in metadata
                meta_data = {"key": key, "result_type": result_type, "timestamp": str(datetime.now())}
                
                # Handling complex dict data in metadata (chroma metadata only supports str/int/float)
                # So we won't store full data in semantic cache metadata, just the key.
                # When a semantic hit occurs, we use the key to fetch from L1/L2.
                query_embedding = self.embeddings.embed_query(query)
                self.semantic_collection.upsert(
                    documents=[query],
                    embeddings=[query_embedding],
                    metadatas=[meta_data],
                    ids=[key]
                )
            except Exception as e:
                logger.error(f"Failed to set L3 Cache: {e}")

    def get_cache(self, key: str) -> Optional[CachedResult]:
        # 1. Check L1
        if key in self.l1_cache:
            return self.l1_cache[key]
            
        # 2. Check L2
        if self.redis_connected:
            try:
                data_str = self.redis_client.get(key)
                if data_str:
                    cached_result = CachedResult.model_validate_json(data_str)
                    # Restore to L1 for faster subsequent access
                    self.l1_cache[key] = cached_result
                    return cached_result
            except Exception as e:
                logger.error(f"Failed to get L2 Cache: {e}")
                
        return None

    def search_semantic_cache(self, query: str, threshold: float = 0.95) -> Optional[CachedResult]:
        """
        L3 Semantic Search. Finds similar queries.
        If similarity is high, returns the cached result.
        """
        if not self.chroma_connected:
            return None
            
        try:
            query_embedding = self.embeddings.embed_query(query)
            results = self.semantic_collection.query(
                query_embeddings=[query_embedding],
                n_results=1
            )
            
            if results and results['distances'] and len(results['distances'][0]) > 0:
                distance = results['distances'][0][0]
                # Chroma uses cosine distance. Distance 0 is exact match.
                # Threshold for similarity: 1 - distance > threshold
                similarity = 1.0 - distance
                if similarity >= threshold:
                    key = results['ids'][0][0]
                    # Fetch actual data from L1 or L2 using the key
                    return self.get_cache(key)
        except Exception as e:
            logger.error(f"L3 Semantic Cache search failed: {e}")
            
        return None
