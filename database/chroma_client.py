import os
import chromadb
from chromadb import EmbeddingFunction, Documents, Embeddings
from sentence_transformers import SentenceTransformer

class MultilingualEmbeddingFunction(EmbeddingFunction):
    """
    Custom embedding function for ChromaDB using SentenceTransformers.
    Uses 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
    to support Japanese and Vietnamese language queries.
    """
    def __init__(self, model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"):
        self.model = SentenceTransformer(model_name)

    def __call__(self, input: Documents) -> Embeddings:
        # Embed the document chunks / queries
        embeddings = self.model.encode(input, convert_to_numpy=True)
        return embeddings.tolist()

def get_chroma_client(persist_directory: str):
    """
    Initializes and returns a ChromaDB PersistentClient.
    """
    os.makedirs(persist_directory, exist_ok=True)
    return chromadb.PersistentClient(path=persist_directory)

def get_embedding_function():
    """
    Returns the multilingual embedding function.
    """
    return MultilingualEmbeddingFunction()
