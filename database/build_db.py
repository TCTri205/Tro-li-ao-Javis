import os
import re
import sys

# Configure stdout and stderr to output UTF-8 text on Windows
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Add parent directory to sys.path so we can import from database package
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.chroma_client import get_chroma_client, get_embedding_function

def parse_company_doc(file_path):
    """
    Parses company profiles (AJ_technologies_ja.md and VJ_technologies_ja.md) into sections.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    filename = os.path.basename(file_path)
    company_name = "AJ Technologies" if "AJ" in filename else "VJ Technologies"
    
    lines = content.splitlines()
    chunks = []
    
    current_title = "Overview"
    current_content = []
    
    for line in lines:
        # Match lines starting with a number followed by dot like "1. 基本情報"
        match = re.match(r'^([1-9]\.\s*.*)', line)
        if match:
            # Save the previous section
            if current_content:
                text = "\n".join(current_content).strip()
                if text:
                    chunks.append(create_company_chunk(text, current_title, filename, company_name))
            # Truncate section_title: keep only "N. セクション名" (heading only, no inline text)
            # Regex: number-dot, then the heading words before any long inline sentence begins
            raw_title = match.group(1).strip()
            # Split at first occurrence of 2+ spaces or a sentence-starting pattern
            # Simpler: take the first space-separated tokens up to 4 words max
            parts = raw_title.split()
            current_title = " ".join(parts[:4]).strip()
            current_content = []
        else:
            current_content.append(line)
            
    # Save the last section
    if current_content:
        text = "\n".join(current_content).strip()
        if text:
            chunks.append(create_company_chunk(text, current_title, filename, company_name))
            
    return chunks

def create_company_chunk(text, section_title, filename, company_name):
    """
    Helper to construct document chunks with metadata for company profiles.
    """
    # Determine category
    category = "general_info"
    if ("基本情報" in section_title or section_title == "Overview"
            or "企業関係" in section_title or "ビジョンとミッション" in section_title):
        category = "general_info"
    elif "事業領域" in section_title or "主要製品" in section_title:
        category = "products"
    elif "製品・機能" in section_title or "サービス" in section_title:
        category = "features"
        
    # Detect product names
    product_names = []
    for prod in ["ホムすん", "ラクかりex", "DX-ASAP", "Energy Japan", "GoEMON"]:
        if prod in text or prod in section_title:
            product_names.append(prod)
            
    product_name = ", ".join(product_names) if product_names else ""
    
    # Combine title and text for semantic embedding richness
    full_text = f"{company_name} - {section_title}\n{text}"
    
    return {
        "content": full_text,
        "metadata": {
            "source_file": filename,
            "category": category,
            "product_name": product_name,
            "company_name": company_name,
            "section_title": section_title
        }
    }

def map_section(header):
    """
    Maps meeting summary section titles to English identifiers.
    """
    if "基本情報" in header:
        return 1, "basic_info"
    elif "目的・背景" in header:
        return 2, "purpose"
    elif "ヒアリング" in header or "顧客ニーズ" in header:
        return 3, "needs"
    elif "提案内容" in header or "商談の進捗" in header:
        return 4, "proposals"
    elif "課題・懸念点" in header:
        return 5, "concerns"
    elif "次回アクション" in header:
        return 6, "next_actions"
    return 0, "unknown"

def parse_summary_meeting(file_path):
    """
    Parses meeting summary transcripts (sumary_mau.md) into 6 sections.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    filename = os.path.basename(file_path)
    
    # Try to extract customer name from text.
    # NOTE: In sample data (sumary_mau.md) names are redacted (blank placeholders),
    # so customer_name will be empty. Will be populated with real transcripts.
    customer_match = re.search(r'来訪者は\s*(.*?)\s*であり', content)
    customer_name = customer_match.group(1).strip() if customer_match else ""
    
    # Standard headers in sumary_mau.md:
    # １. 基本情報
    # ２. 商談の目的・背景
    # ３. ヒアリング内容（顧客ニーズ）
    # ４. 提案内容・商談の進捗
    # ５. 課題・懸念点
    # ６. 次回アクション
    
    # Regex to capture the section headers and contents
    headers = [
        "基本情報",
        "商談の目的・背景",
        "ヒアリング内容（顧客ニーズ）",
        "提案内容・商談の進捗",
        "課題・懸念点",
        "次回アクション"
    ]
    
    header_positions = []
    for h in headers:
        # Match standard or full width numbers followed by dot and spaces and header name
        pattern = re.compile(rf'(?:[1-6１-６]\s*[\.．]\s*)?{re.escape(h)}')
        match = pattern.search(content)
        if match:
            header_positions.append((h, match.start(), match.end()))
            
    header_positions.sort(key=lambda x: x[1])
    chunks = []
    
    for i in range(len(header_positions)):
        header_text, start, end = header_positions[i]
        next_start = header_positions[i+1][1] if i + 1 < len(header_positions) else len(content)
        sec_content = content[start:next_start].strip()
        
        section_id, section_name = map_section(header_text)
        
        chunks.append({
            "content": sec_content,
            "metadata": {
                "source_file": filename,
                "section_id": section_id,
                "section_name": section_name,
                "customer_name": customer_name
            }
        })
        
    return chunks

def build_database():
    workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    docs_dir = os.path.join(workspace_dir, "docs")
    db_dir = os.path.join(workspace_dir, "database", "database.db")
    
    print(f"Docs directory: {docs_dir}")
    print(f"Database directory: {db_dir}")
    
    # 1. Parse documents
    aj_doc_path = os.path.join(docs_dir, "AJ_technologies_ja.md")
    vj_doc_path = os.path.join(docs_dir, "VJ_technologies_ja.md")
    summary_path = os.path.join(docs_dir, "sumary_mau.md")
    
    company_chunks = []
    if os.path.exists(aj_doc_path):
        print(f"Parsing {aj_doc_path}...")
        company_chunks.extend(parse_company_doc(aj_doc_path))
    if os.path.exists(vj_doc_path):
        print(f"Parsing {vj_doc_path}...")
        company_chunks.extend(parse_company_doc(vj_doc_path))
        
    summary_chunks = []
    if os.path.exists(summary_path):
        print(f"Parsing {summary_path}...")
        summary_chunks.extend(parse_summary_meeting(summary_path))
        
    print(f"Total company chunks parsed: {len(company_chunks)}")
    print(f"Total summary chunks parsed: {len(summary_chunks)}")
    
    # 2. Setup ChromaDB client and embedding function
    print("Initializing embedding function...")
    embedding_func = get_embedding_function()
    
    print("Connecting to ChromaDB...")
    client = get_chroma_client(db_dir)
    
    # 3. Populate aj_docs collection
    print("Setting up 'aj_docs' collection...")
    # Delete existing collection if it exists to refresh database
    try:
        client.delete_collection("aj_docs")
        print("Deleted existing 'aj_docs' collection.")
    except Exception:
        pass
    aj_collection = client.create_collection("aj_docs", embedding_function=embedding_func)
    
    # Add items to aj_docs
    if company_chunks:
        ids = [f"aj_doc_chunk_{i}" for i in range(len(company_chunks))]
        documents = [chunk["content"] for chunk in company_chunks]
        metadatas = [chunk["metadata"] for chunk in company_chunks]
        
        aj_collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )
        print(f"Added {len(company_chunks)} documents to 'aj_docs' collection.")
        
    # 4. Populate summary_transcripts collection
    print("Setting up 'summary_transcripts' collection...")
    try:
        client.delete_collection("summary_transcripts")
        print("Deleted existing 'summary_transcripts' collection.")
    except Exception:
        pass
    summary_collection = client.create_collection("summary_transcripts", embedding_function=embedding_func)
    
    # Add items to summary_transcripts
    if summary_chunks:
        ids = [f"summary_chunk_{i}" for i in range(len(summary_chunks))]
        documents = [chunk["content"] for chunk in summary_chunks]
        metadatas = [chunk["metadata"] for chunk in summary_chunks]
        
        summary_collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )
        print(f"Added {len(summary_chunks)} documents to 'summary_transcripts' collection.")
        
    print("Database built successfully!")

if __name__ == "__main__":
    build_database()
