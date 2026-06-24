import os
import logging
from typing import List, Dict, Any, Optional
import chromadb
from langchain_ollama import OllamaEmbeddings

logger = logging.getLogger(__name__)

class RAGEngine:
    def __init__(self, persist_directory: str = "chroma_db"):
        self.persist_directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), persist_directory)
        self.client = chromadb.PersistentClient(path=self.persist_directory)
        
        # We use Gemini Embeddings
        self.embeddings = OllamaEmbeddings(model="nomic-embed-text")
        
        # Create or get collection
        self.collection_name = "transcripts_collection"
        self.collection = self.client.get_or_create_collection(name=self.collection_name)

    def search_transcript(self, query: str, transcript_id_filter: Optional[str] = None, top_k: int = 5) -> List[Dict[str, Any]]:
        # Generate embedding for the query
        query_embedding = self.embeddings.embed_query(query)
        
        # Build where filter
        where_filter = {}
        if transcript_id_filter:
            where_filter = {"transcript_id": transcript_id_filter}

        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_filter if where_filter else None
            )
            
            formatted_results = []
            if results and results['documents'] and len(results['documents'][0]) > 0:
                for i in range(len(results['documents'][0])):
                    formatted_results.append({
                        "content": results['documents'][0][i],
                        "metadata": results['metadatas'][0][i] if results['metadatas'] else {}
                    })
            return formatted_results
        except Exception as e:
            logger.error(f"RAG Search failed: {e}")
            return []
