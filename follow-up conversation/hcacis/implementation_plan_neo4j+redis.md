# HCACIS: Nâng cấp Kiến trúc Production-grade (GraphRAG, Neo4j, Redis)

Dựa trên yêu cầu thiết kế hệ thống chuyên sâu của bạn, HCACIS hiện tại vẫn còn ở mức nguyên mẫu (với in-memory graph và cache cơ bản). Để hệ thống thực sự đáp ứng tiêu chuẩn **Production-grade, Graph-based Reasoning và Multi-tier Cache**, tôi đề xuất lộ trình nâng cấp toàn diện như sau:

## 1. Cập nhật Infrastructure (Docker & Thư viện)
Để có đủ "vũ khí" xây dựng Layer 2 và 3, chúng ta cần bổ sung hai cơ sở dữ liệu quan trọng vào stack:
#### [MODIFY] [docker-compose.yml](file:///d:/javis_text2sql/numeric_sql_tool_v2/docker-compose.yml)
- **Thêm Neo4j:** Dùng làm Context Graph Engine chuyên nghiệp (thay thế cho NetworkX hiện tại) để giải quyết Coreference (ví dụ: truy vết "Ông ấy" -> "Kumagai" trong meeting).
- **Thêm Redis:** Dùng làm L2 Cache (lưu trữ kết quả tạm thời với TTL 30-60 phút).

#### [MODIFY] [requirements.txt](file:///d:/javis_text2sql/hcacis/requirements.txt)
- Thêm `neo4j` (driver kết nối đồ thị).
- Thêm `redis` (driver kết nối cache).

## 2. Nâng cấp chi tiết từng Layer

### Layer 1: Follow-up Detector
#### [MODIFY] [layer1_detector.py](file:///d:/javis_text2sql/hcacis/layer1_detector.py)
- Bổ sung **Few-shot prompting**: Thêm 3-5 ví dụ chuẩn vào prompt để LLM nhận diện cực kỳ chính xác các loại `relation_type` (same_entity, topic_shift...).
- **Rule-based fallback**: Thêm cơ chế regex quét nhanh các từ khóa đại từ (nó, ấy, kia, その, あの) trước khi gọi LLM để tối ưu tốc độ.

### Layer 2: Context Memory Manager + Entity Resolver (Cốt lõi)
#### [MODIFY] [context_graph.py](file:///d:/javis_text2sql/hcacis/context_graph.py)
- Chuyển đổi toàn bộ từ `NetworkX` sang **Neo4j Graph Database**.
- Các thực thể (Entities) như `Meeting_123`, `Person_A` sẽ được lưu thành các **Node**.
- Các quan hệ (Relations) như `has_participant`, `has_transcript` sẽ thành **Edges**.
- Viết lại hàm `resolve_coreference` để dùng **Graph Traversal (Cypher query)** quét các node lân cận tìm kiếm ngữ cảnh gốc thay vì chỉ search text.

### Layer 3: Retrieval Planner & Multi-tier Cache
#### [MODIFY] [cache_manager.py](file:///d:/javis_text2sql/hcacis/cache_manager.py)
Triển khai hệ thống **Cache 3 lớp**:
- **L1 (RAM):** Biến Dictionary python cho data nóng hổi trong turn.
- **L2 (Redis):** Cache kết quả SQL/RAG có TTL (thời gian sống) khoảng 30 phút.
- **L3 (Semantic Cache - ChromaDB):** Tạo một Collection mới trong ChromaDB chuyên lưu trữ các vector của `query`. Nếu User hỏi một câu có ý nghĩa tương đương (Cosine Similarity > 0.9) với câu cũ, trả ngay kết quả từ Cache mà không cần gọi Database hay RAG.

#### [MODIFY] [layer3_planner.py](file:///d:/javis_text2sql/hcacis/layer3_planner.py)
- **Context-bound SQL & RAG:** Khi query SQL thành công, trích xuất ID (như `transcript_id`) ném vào Neo4j. Khi User hỏi follow-up, Planner sẽ lấy ID này từ Neo4j để làm **Filter** cho truy vấn tiếp theo, tránh phải quét lại toàn bộ dữ liệu (Partial Fetch).

### Layer 4: Answer Generator
#### [MODIFY] [layer4_generator.py](file:///d:/javis_text2sql/hcacis/layer4_generator.py)
- Thêm **Verification Step (Kiểm chứng):** Bổ sung chỉ thị nghiêm ngặt vào Prompt để ép LLM phải trích xuất và kèm theo Citations (nguồn trích dẫn) dựa trên dữ liệu Cache. Không bịa data.

## User Review Required

> [!IMPORTANT]
> Để nâng cấp hệ thống này, **việc sử dụng Docker để chạy Neo4j và Redis là bắt buộc**.
> Nếu bạn đồng ý với kế hoạch kiến trúc trên, tôi sẽ bắt đầu bằng việc:
> 1. Sửa file `docker-compose.yml` và yêu cầu bạn chạy lệnh `docker compose up -d` để tải Neo4j và Redis về máy.
> 2. Lần lượt viết lại Layer 2 (Neo4j) và Layer 3 (Redis + Semantic Chroma).
> 
> Xin chờ xác nhận của bạn!
