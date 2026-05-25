import os
import sys
import chromadb
from typing import List, Dict, Any, Optional

# Configure stdout to output UTF-8 text on Windows if run directly
if __name__ == "__main__":
    if sys.platform.startswith('win'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.chroma_client import get_chroma_client, get_embedding_function

class Document:
    """
    Standard Document class representing retrieved context chunks.
    """
    def __init__(self, page_content: str, metadata: Optional[Dict[str, Any]] = None):
        self.page_content = page_content
        self.metadata = metadata if metadata is not None else {}

    def __repr__(self):
        return f"Document(page_content='{self.page_content[:50]}...', metadata={self.metadata})"


class JavisRetriever:
    """
    Retriever class to route and query ChromaDB collections based on user intent.
    """
    def __init__(self, persist_directory: str):
        # Khởi tạo persistent client kết nối tới ChromaDB
        self.client = get_chroma_client(persist_directory)
        
        # Load embedding function to ensure query is embedded using correct model
        self.embedding_func = get_embedding_function()
        
        # Load các collection tương ứng với embedding function
        self.aj_collection = self.client.get_collection("aj_docs", embedding_function=self.embedding_func)
        self.summary_collection = self.client.get_collection("summary_transcripts", embedding_function=self.embedding_func)

    def retrieve(self, query: str, intent: str) -> List[Document]:
        """
        Thực hiện tìm kiếm tương đồng trên Collection tương ứng dựa theo Intent.
        
        :param query: Câu hỏi truy vấn của người dùng.
        :param intent: Phân loại ý định ('company_info' hoặc 'meeting_summary').
        :return: list[Document] chứa ngữ cảnh và metadata tương ứng.
        """
        # Routing logic lựa chọn Collection đích
        if intent == "company_info":
            target_collection = self.aj_collection
        elif intent == "meeting_summary":
            target_collection = self.summary_collection
        else:
            raise ValueError(f"Intent không hợp lệ: '{intent}'. Chỉ chấp nhận 'company_info' hoặc 'meeting_summary'.")

        # Truy vấn tìm kiếm ngữ nghĩa (semantic search)
        results = target_collection.query(
            query_texts=[query],
            n_results=3
        )

        # Chuyển đổi định dạng kết quả thô từ ChromaDB sang danh sách đối tượng Document
        document_list = []
        if results and 'documents' in results and len(results['documents']) > 0:
            for idx in range(len(results['documents'][0])):
                content = results['documents'][0][idx]
                metadata = results['metadatas'][0][idx] if 'metadatas' in results else {}
                
                # Khởi tạo đối tượng Document
                doc = Document(page_content=content, metadata=metadata)
                document_list.append(doc)
                
        return document_list


# Ví dụ sử dụng kiểm thử tích hợp
if __name__ == "__main__":
    # Tìm đường dẫn tương đối tới database.db
    workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_dir = os.path.join(workspace_dir, "database", "database.db")
    
    retriever = JavisRetriever(persist_directory=db_dir)
    
    # 1. Truy xuất thông tin công ty AJ Docs
    print("=== TEST RETRIEVAL: AJ DOCS ===")
    company_docs = retriever.retrieve(
        query="Nền tảng DX ホムすん có tính năng gì?",
        intent="company_info"
    )
    for doc in company_docs:
        print(f"Content: {doc.page_content[:150]}...")
        print(f"Metadata: {doc.metadata}")
        print("-" * 40)

    # 2. Truy xuất thông tin tóm tắt cuộc họp
    print("\n=== TEST RETRIEVAL: MEETING SUMMARY ===")
    meeting_docs = retriever.retrieve(
        query="Khách hàng lo lắng điều gì và muốn mua nhà ở đâu?",
        intent="meeting_summary"
    )
    for doc in meeting_docs:
        print(f"Content: {doc.page_content[:150]}...")
        print(f"Metadata: {doc.metadata}")
        print("-" * 40)
