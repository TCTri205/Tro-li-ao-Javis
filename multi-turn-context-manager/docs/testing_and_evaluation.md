# Kiểm Thử và Đánh Giá (Testing & Evaluation)
## Quản Lý Ngữ Cảnh Hội Thoại Đa Lượt (Multi-turn Context Management)

Tài liệu này đặc tả chi tiết kế hoạch kiểm thử, các kịch bản đánh giá (Test Cases) và bộ công cụ đo lường hiệu năng tự động (Benchmark Suite) của hệ thống điều phối ngữ cảnh phiên bản v3.

---

## 1. Kịch Bản Kiểm Thử Chi Tiết (Test Scenarios)

Dưới đây là các kịch bản hội thoại thực tế được sử dụng để đánh giá độ chính xác của bộ điều phối v3:

### Kịch Bản 1: Hỏi Tiếp Cận (Follow-up - Cache Hit)
* **Lượt 1:** User: *"Cuộc gọi GT_04 ngày 4/5/2026 kéo dài bao lâu?"*
  * **Hành vi:** `needs_retrieval` = `"full"`, chạy pipeline `SQL` truy vấn `duration_seconds` trong bảng `transcripts`. Lưu kết quả vào Cache Slot 1 (`topic_key = "GT_04_duration"`), đặt `refreshed_at` và `last_accessed_at = NOW()`.
* **Lượt 2:** User: *"Ai đã thực hiện cuộc gọi **đó**?"*
  * **Hành vi:** `is_follow_up` = `true`, `needs_retrieval` = `"none"`. Định tuyến Tier 1 sử dụng Entity Index match đại từ *"đó"* thành công để ánh xạ tới cuộc gọi GT_04. Hệ thống đọc trực tiếp dữ liệu từ bảng Cold (`session_context_payload`) của Slot 1 (chứa `participants` gồm Yokobori và Nakahara Rinka) và phản hồi. Cập nhật `last_accessed_at = NOW()`. Không gọi lại SQL.

### Kịch Bản 2: Đổi Chủ Đề Đột Ngột (Topic Switching - Cache Invalidation)
* **Lượt 1:** User: *"Cuộc gọi GT_04 ngày 4/5/2026 kéo dài bao lâu?"*
  * **Hành vi:** Chạy pipeline SQL gốc, lưu vào Cache Slot 1 (`topic_key = "GT_04_duration"`).
* **Lượt 2:** User: *"Ngày 3/5/2026 có cuộc gọi nào về việc xem nhà không?"*
  * **Hành vi:** `needs_retrieval` = `"full"`, định tuyến Tier 1 hoặc Tier 2 phát hiện Topic Shift, target pipeline là `SQL`/`RAG` (tìm kiếm cuộc gọi GT_03 của Shimada hỏi về Asset Japan xem nhà). Hệ thống thực thi để lấy dữ liệu và lưu vào một cache slot mới độc lập (Slot 2 - `topic_key = "GT_03_viewing"`) với timestamps mới. **Slot 1 (GT_04_duration) được giữ nguyên trong cơ sở dữ liệu (không bị ghi đè)** để sẵn sàng phục vụ việc quay lại chủ đề cũ ở Kịch bản 4.

### Kịch Bản 3: Hỏi Thiếu Chủ Ngữ (Ellipsis / Contextual Recall & Partial Fetch)
* **Lượt 1:** User: *"Tìm các cuộc gọi của AJ Technologies Yamashita tìm Kase."*
  * **Hành vi:** `needs_retrieval` = `"full"`, chạy pipeline `SQL`/`RAG` tìm kiếm `GT_06`. Tạo Cache Slot 1 (`topic_key = "GT_06_yamashita_kase"`).
* **Lượt 2:** User: *"Thế còn Tsuji tìm Onoda?"*
  * **Hành vi:** 
    * `is_follow_up` = `true`, `needs_retrieval` = `"partial"`.
    * `relation_type` = `"same_subject_new_param"`.
    * `rewritten_query` = *"Tìm cuộc gọi của AJ Technologies Tsuji tìm Onoda."*.
    * `target_pipeline` = `"SQL"`.
    * `partial_fetch_params` = `{"sql_filter": "WHERE session_id = 'GT_08'"}`.
    * SQL Engine thực thi tối ưu bằng cách tái sử dụng template và tham số lọc từ context cũ, cập nhật dữ liệu. Mọi trường hợp partial fetch đều đi qua LLM để tổng hợp kết quả ngữ cảnh thay vì đi direct path.

### Kịch Bản 4: Quay Lại Chủ Đề Cũ (Switch Back - Cache Hit)
* **Lượt 1:** User: *"Cuộc gọi GT_04 ngày 4/5/2026 kéo dài bao lâu?"* (Lưu vào Cache Slot 1 - `GT_04_duration`)
* **Lượt 2:** User: *"Ngày 3/5/2026 có cuộc gọi nào về việc xem nhà không?"* (Lưu vào Cache Slot 2 - `GT_03_viewing`)
* **Lượt 3:** User: *"Thế ai là người nhận cuộc gọi lúc nãy?"*
  * **Hành vi:** 
    * Định tuyến Tier 1 hoặc Tier 2 phân giải từ chỉ định *"lúc nãy"* (ARRAY search trên `session_entity_index`) và xác định chủ đề quay lại là `GT_04_duration`.
    * Do Slot 1 không bị ghi đè bởi Slot 2, hệ thống thực hiện Switch Back thành công: `needs_retrieval = "none"`, `target_topic_key = "GT_04_duration"`.
    * Đọc dữ liệu trực tiếp từ Slot 1 để trả lời ngay, cập nhật `last_accessed_at = NOW()`.

---

## 1.5. Các Kịch Bản Kiểm Thử Phức Tạp & Nhiễu (Dirty & Complex Test Scenarios)

Để đảm bảo độ tin cậy trong môi trường vận hành thực tế, hệ thống duy trì bộ test case nhiễu và bổ sung các kịch bản kiểm thử nâng cấp v3:

### Bảng Kịch Bản Nhiễu (NEG_001 - NEG_013)

| Mã Test Case | Loại Test Case | Câu Hỏi Đầu Vào (Input) | Ngữ Cảnh Trước Đó (History & Cache) | Kết Quả Kỳ Vọng (Expected Output) |
| :--- | :--- | :--- | :--- | :--- |
| **NEG_001** | Mơ hồ nhiều thực thể | "Cuộc gọi đó nói gì?" | Có cả slot GT_04 và GT_03 hoạt động song song. | Router trả về `needs_retrieval = "full"`, `target_pipeline = MODEL` để LLM chính hỏi lại người dùng làm rõ thực thể, không đoán bừa. |
| **NEG_002** | Topic shift bất ngờ | "À thôi, tìm thông tin về ca sĩ A trên mạng đi." | Đang hỏi về cuộc gọi GT_04. | `needs_retrieval = "full"`, phát hiện Topic Shift, định tuyến sang `target_pipeline = WEB`. |
| **NEG_003** | Hội thoại mới tinh | "Ngày 2/5/2026 có cuộc gọi nào không?" | Chat history rỗng, cache rỗng. | `needs_retrieval = "full"`, `target_pipeline = SQL`, chạy bình thường không crash. |
| **NEG_004** | LLM Router Timeout | "Nội dung cuộc gọi ấy là gì?" | Có cache cuộc gọi hợp lệ nhưng LLM Router bị timeout. | Kích hoạt cơ chế Fallback an toàn: `needs_retrieval = "full"`, chạy lại engine gốc hoặc dùng MODEL để trả lời, không crash luồng. |
| **NEG_005** | Lỗi định dạng JSON | "Nội dung cuộc gọi ấy là gì?" | Có cache hợp lệ nhưng LLM Router trả về JSON sai cú pháp. | Kích hoạt bộ Regex Parser trích xuất JSON hoặc dùng fallback mặc định để chạy an toàn. |
| **NEG_006** | Lỗi chính tả & viết tắt | "Cuoc goi GT_04 keo dai bao lau" | Có cache cuộc gọi GT_04. | Định tuyến Tier 1/2 tự động sửa lỗi, ánh xạ đúng vào slot cuộc gọi, `needs_retrieval = "none"`. |
| **NEG_007** | Trộn ngôn ngữ (Code-mix) | "Thế còn call đó end lúc mấy h?" | Có cache cuộc gọi GT_04. | Giải phân thực thể thay thế thành công, viết lại query: *"Cuộc gọi GT_04 kết thúc lúc mấy giờ?"*, `needs_retrieval = "none"`. |
| **NEG_008** | Hỏi song song nhiều thực thể | "So sánh cuộc gọi GT_04 và GT_06" | Có cache cuộc gọi GT_04. | `needs_retrieval = "full"`, `context_reuse_type = query_rewrite_only`, định tuyến sang `target_pipeline = SQL/MODEL` để tổng hợp. |
| **NEG_009** | Đổi ý liên tục (LRU test) | User hỏi xoay vòng 4 cuộc gọi liên tục: GT_04 -> GT_03 -> GT_06 -> GT_08. | 3 slots cache đang hoạt động. | Thực hiện switch back thành công đối với các topic còn trong cache; evict slot có `last_accessed_at` cũ nhất khi có topic thứ 4. |
| **NEG_010** | Dữ liệu Web quá TTL | "Giá cổ phiếu Mitsubishi hôm nay thế nào?" | Có cache thông tin Mitsubishi nhưng mốc `refreshed_at` cách đây 2 giờ (TTL = 1 giờ). | `check_cache_ttl` trả về `False`, buộc đặt `needs_retrieval = "full"` để gọi lại Web Engine nhằm lấy dữ liệu mới và cập nhật `refreshed_at = NOW()`. |
| **NEG_011** | Tải đồng thời cao (Lock test) | 5 request hỏi tiếp nối gửi đồng thời trong 1 giây cho 1 session. | Có cache đang hoạt động. | Lock Mutex/Queue ở Orchestrator xếp hàng xử lý tuần tự, ghi nhận và phản hồi đúng thứ tự ngữ cảnh, không bị race condition. |
| **NEG_012** | Lỗi Verification (Self-Check) | "Nội dung cuộc gọi GT_04 là gì?" | Có cache nội dung cuộc gọi, nhưng LLM chính sinh thông tin sai lệch so với raw data. | Bộ Verifier phát hiện mâu thuẫn dữ liệu, kích hoạt yêu cầu sinh lại (Regenerate) an toàn trước khi phản hồi người dùng. |
| **NEG_013** | Khớp thực thể nhanh (Entity Index) | "Anh ấy nói gì?" | Bảng `session_entity_index` ánh xạ "Anh ấy" -> "Yokobori" trong cuộc gọi GT_04 đang hoạt động. | Tier 1 phát hiện khớp trực tiếp trong bảng index, thiết lập `needs_retrieval = "none"` và đọc cache ngay lập tức (~2ms). |
| **FIX_001** | Lỗi Embedding Timeout | "Tìm các cuộc gọi của AJ Technologies" | Session bình thường. Mô hình embedding phản hồi chậm > 1.0 giây. | `_safe_embed()` ngắt kết nối sau 1s, trả về `None`, đặt `embedding_failed = True`. Tier 1 bypass nhanh sang Tier 2 LLM Router với `routing_reason = 'embedding_failure'`. |
| **FIX_002** | Trả Về Vector Rỗng (0-vector) | Chứa ký tự lạ / khoảng trắng | Session bình thường. Mô hình embedding trả về vector 0. | `_safe_embed()` phát hiện vector 0, ném biệt lệ, trả về `None`. Tier 1 tự động hạ cấp chuyển request sang Tier 2 LLM Router để định vị intent. |
| **FIX_003** | Khóa Dòng Tránh Tranh Chấp LRU | "Thế còn Tsuji tìm Onoda?" (Partial) | Có Slot 1 đang chạy Engine SQL. Lệnh LRU cleanup kích hoạt song song. | Giao dịch SQL Partial lấy khóa `SELECT ... FOR UPDATE` trên Slot 1 thành công. Tiến trình LRU cleanup bị chặn, không thể xóa Slot 1 cho tới khi transaction kết thúc. |
| **FIX_004** | Self-check Sửa Sai Thành Công | "Tóm tắt cuộc gọi GT_04" | Slot 1 hoạt động. LLM sinh sai lệch số lượng người tham gia ở lượt đầu. | Bộ Verifier so khớp phát hiện lỗi, inject instruction sửa đổi. LLM sinh lại ở Lượt 2 đạt yêu cầu. Trả về câu trả lời chuẩn xác với `answer_confidence = 'high'`. |
| **FIX_005** | Quá Lượt Self-check (Hallucination) | "Chi tiết cuộc gọi GT_04" | Slot 1 hoạt động. LLM liên tục tự chế số liệu không có trong DB sau 2 lượt sửa. | Hết `max_retries = 2`, Verifier tự động trả về câu trả lời thô kèm chuỗi cảnh báo an toàn ở cuối câu, đồng thời ghi nhận `answer_confidence = 'low'`. |
| **FIX_006** | Ghi Chỉ Mục Thực Thể Web | "Thông tin về AJ Technologies" | Web Search trả về kết quả giới thiệu công ty. | `EntityExtractor` chạy hậu kỳ, phân tích kết quả web, lấy tên AJ Technologies và các đại từ "nó", "công ty đó" đưa vào bảng `session_entity_index`. |
| **FIX_007** | Refresh Cache Động Khi Quá Hạn | "Giá cổ phiếu Mitsubishi hôm nay" | Có cache Mitsubishi cũ nhưng timestamp `refreshed_at` cách đây 3 giờ. | Kiểm tra `check_cache_ttl` trả về `False`. Router chỉ định `use_cache = false`, chạy lại Web Engine để lấy thông tin mới nhất và làm mới timestamps. |
| **FIX_008** | Xếp Hàng Khóa Advisory Lock | 2 click đúp đồng thời: "Tìm cuộc gọi GT_04", "Thế còn GT_03?" | Session hoạt động. | Request 2 thử lấy `pg_try_advisory_xact_lock` nhưng bị giữ lại ở loop chờ. Request 1 xử lý xong và giải phóng lock, request 2 mới được đi tiếp. Ngữ cảnh ghi nhận tuần tự. |
| **FIX_009** | Timeout Khóa Advisory Lock | Session bị treo do tài nguyên DB nghẽn | Session đang xử lý một transaction nặng. | Request sau chờ đợi quá `timeout_seconds = 8.0` trên Advisory Lock. Ném lỗi TimeoutError để giải phóng luồng ứng dụng nhanh, không gây nghẽn RAM. |
| **FIX_010** | Cập Nhật Vector Ngăn Chặn Lệch Tâm | "Thế còn cuộc gọi GT_08?" (Sau khi hỏi GT_06) | Slot 1 đang hoạt động. | `update_cache_slot` sinh embedding cho rewritten query mới và cập nhật đè lên cột `query_embedding` của Slot 1. Khoảng cách ngữ nghĩa các câu sau được tính toán chuẩn xác. |

### Các Kịch Bản Phức Tạp Bổ Sung (NEG_014 - NEG_019)

| Mã Test Case | Loại Test Case | Câu Hỏi Đầu Vào (Input) | Ngữ Cảnh Trước Đó (History & Cache) | Kết Quả Kỳ Vọng (Expected Output) |
| :--- | :--- | :--- | :--- | :--- |
| **NEG_014** | Trùng tên thực thể mơ hồ | "ông ấy nói gì?" | Lịch sử chứa hai người nam: "Kase-san" (GT_06) và "Ishihara-san" (GT_07). | Entity index không thể trả về 1 kết quả duy nhất. Tier 1 bypass sang Tier 2 LLM Router để tự động sinh câu hỏi làm rõ đối tượng. |
| **NEG_015** | Quay vòng liên tục 3 chủ đề | Xoay vòng hỏi: Mitsubishi -> SQL GT_04 -> RAG GT_06. | Đã có đủ 3 slots cache cho cả 3 chủ đề này. | Không xảy ra hiện tượng Eviction vì số slots tối đa là 3. Cả 3 lượt truy cập đều trúng Cache Hit ở bảng Hot nhờ `last_accessed_at` tự cập nhật liên tục. |
| **NEG_016** | SQL Thay Đổi Schema Đột Ngột | "Thời lượng cuộc gọi GT_04" | Có SQL cache cũ. Bảng transcripts thật bị xóa cột duration_seconds. | SQL Engine lỗi. Circuit Breaker bắt ngoại lệ, chuyển trạng thái OPEN. Hạ cấp sang parametric MODEL, trả về câu trả lời parametric kèm báo lỗi tinh tế. |
| **NEG_017** | Token Bloat RAG PDF Cực Lớn | "Chi tiết cuộc gọi GT_06" | Bản ghi thoại 100 trang trong Cold payload. | Nhờ phân tách Hot/Cold, các lệnh định tuyến và LRU eviction chỉ quét bảng Hot siêu nhẹ. Cold payload dung lượng lớn chỉ được load duy nhất khi trúng cache hit. |
| **NEG_018** | Web Search Bị Giới Hạn Tần Suất | "Thông tin cổ phiếu Mitsubishi" | Web API trả về lỗi HTTP 429 (Too Many Requests). | WEB Circuit Breaker kích hoạt trạng thái OPEN sau 3 lần lỗi liên tiếp. Hạ cấp nhanh sang parametric MODEL trong 30s cooldown. |
| **NEG_019** | Trộn lẫn đại từ Anh-Việt | "nó và cái doc đó" | Thực thể liên kết mảng display_names: {"GT_04.txt", "nó", "cái doc đó"}. | SQL lookup trên `display_names` sử dụng ARRAY operator khớp chính xác cả hai cụm từ chỉ định và định tuyến thành công sang Slot tương ứng. |

---

## 2. Các Chỉ Số Đo Lường Hiệu Năng Nâng Cao (Evaluation Metrics)

Hệ thống đo đạc và báo cáo các chỉ số vận hành thực tế sau:

### 2.1. Routing Accuracy (Độ chính xác của Bộ định tuyến)
* **Công thức:** `(Số lượt định tuyến đúng / Tổng số lượt chat) * 100%`
* **Mục tiêu:** > 95% trên bộ test suite chuẩn (bao gồm cả Tier 1 và Tier 2).

### 2.2. Latency Saved & p95/p99 Latency (Độ trễ)
* **Độ trễ trung bình tiết kiệm được:** `T_saved = T_original_pipeline - T_cache_read`
  * **Mục tiêu:** Tiết kiệm trung bình > 400ms trên mỗi lượt chat có sử dụng Cache.
* **p95/p99 Latency:** Độ trễ ở phân vị thứ 95 và 99 để đánh giá tính ổn định.
  * **Mục tiêu:** p95 Latency < 200ms đối với Fast Path (Tier 1 + Cache Hit + Direct Answer) và < 900ms đối với Slow Path (Tier 2 + Engine Run + Final LLM).

### 2.3. Cache Hit Rate (Tỷ lệ sử dụng Cache)
* **Công thức:** `(Số lượt use_cache = true / Tổng số lượt chat follow-up) * 100%`

### 2.4. Answer Correctness (Độ chính xác câu trả lời)
* **Đo lường:** Đánh giá tính chính xác của câu trả lời cuối cùng so với bộ câu trả lời vàng (Ground Truth) bằng mô hình giám sát (LLM-as-a-judge).
* **Mục tiêu:** > 98%.

### 2.5. Groundedness (Tính trung thực / Chống ảo giác)
* **Đo lường:** Tỷ lệ câu trả lời hoàn toàn dựa trên ngữ cảnh được cung cấp bởi cache/engine payload và không tự sinh ra thông tin ảo giác ngoài nguồn (Hallucination).
* **Mục tiêu:** 100% (được đánh giá bởi LLM judge).

### 2.6. Stale-Cache Rate (Tỷ lệ cache quá hạn)
* **Công thức:** `(Số lượt sử dụng dữ liệu cache quá TTL / Tổng số lượt sử dụng cache) * 100%`
* **Mục tiêu:** 0% (hệ thống phải tự động refresh dữ liệu khi hết hạn TTL).

### 2.7. Concurrency Failure Rate (Tỷ lệ lỗi xử lý đồng thời)
* **Công thức:** `(Số request bị lỗi/bị drop do tranh chấp đồng thời / Tổng số request gửi song song) * 100%`
* **Mục tiêu:** 0% (nhờ cơ chế xếp hàng tuần tự hóa session).

---

## 3. Cấu Trúc Mã Nguồn Đánh Giá (Evaluation Script Structure)

Dưới đây là cấu trúc giả mã (pseudocode) cho bộ công cụ đánh giá hiệu năng tự động tích hợp v3:

```python
import time
import asyncio
import statistics

class BenchmarkSuite:
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.results = []

    async def run_scenario(self, scenario_name, queries):
        print(f"=== Running Scenario: {scenario_name} ===")
        session_id = f"test_{int(time.time())}"
        scenario_data = []

        for idx, query in enumerate(queries):
            start_time = time.perf_counter()
            
            # Thực thi xử lý câu hỏi qua điều phối Orchestrator
            response, metadata = await self.orchestrator.handle(session_id, query)
            
            end_time = time.perf_counter()
            latency = (end_time - start_time) * 1000  # ms

            step_result = {
                "turn": idx + 1,
                "query": query,
                "rewritten_query": metadata.get("rewritten_query"),
                "needs_retrieval": metadata.get("needs_retrieval"), # 'none' | 'partial' | 'full'
                "relation_type": metadata.get("relation_type"), # 'same_entity' | 'same_subject_new_param' | ...
                "target_pipeline": metadata.get("target_pipeline"),
                "routing_tier": metadata.get("routing_tier"), # 'tier_1' hoặc 'tier_2'
                "routing_method": metadata.get("routing_method"), # 'heuristics' | 'embeddings' | 'llm_router' | 'fallback'
                "embedding_failed": metadata.get("embedding_failed", False), # True/False
                "direct_answer_used": metadata.get("direct_answer_used"), # True/False
                "self_check_passed": metadata.get("self_check_passed"), # True/False
                "self_check_retries": metadata.get("self_check_retries", 0), # Số lần retry: 0, 1, 2
                "answer_confidence": metadata.get("answer_confidence", "high"), # 'high' | 'low'
                "latency_ms": latency
            }
            scenario_data.append(step_result)
            
            print(f"Turn {idx+1}: '{query}' | Trễ: {latency:.2f}ms | Method: {step_result['routing_method'].upper()} | Retrieval: {step_result['needs_retrieval'].upper()} | Direct Ans: {step_result['direct_answer_used']} | Self Check Retries: {step_result['self_check_retries']} | Confidence: {step_result['answer_confidence'].upper()}")

        self.results.append({
            "scenario": scenario_name,
            "turns": scenario_data
        })

    def print_report(self):
        print("
" + "="*50 + "
BÁO CÁO ĐÁNH GIÁ HIỆU NĂNG V3
" + "="*50)
        all_turns = [turn for s in self.results for turn in s["turns"]]
        
        cache_hits = [t for t in all_turns if t["needs_retrieval"] == "none"]
        partial_hits = [t for t in all_turns if t["needs_retrieval"] == "partial"]
        tier1_routes = [t for t in all_turns if t["routing_tier"] == "tier_1"]
        direct_answers = [t for t in all_turns if t["direct_answer_used"] == True]
        self_check_failed = [t for t in all_turns if t["self_check_passed"] == False]
        embedding_failures = [t for t in all_turns if t["embedding_failed"] == True]
        low_confidence_answers = [t for t in all_turns if t["answer_confidence"] == "low"]
        
        # Thống kê phương thức định tuyến
        method_counts = {
            "heuristics": len([t for t in all_turns if t["routing_method"] == "heuristics"]),
            "embeddings": len([t for t in all_turns if t["routing_method"] == "embeddings"]),
            "llm_router": len([t for t in all_turns if t["routing_method"] == "llm_router"]),
            "fallback": len([t for t in all_turns if t["routing_method"] == "fallback"])
        }
        
        p95_latency = statistics.quantiles([t["latency_ms"] for t in all_turns], n=20)[18] # Phân vị 95%
        p99_latency = statistics.quantiles([t["latency_ms"] for t in all_turns], n=100)[98] # Phân vị 99%
        
        print(f"Tổng số lượt kiểm thử: {len(all_turns)}")
        print(f"Số lượt định tuyến nhanh ở Tier 1: {len(tier1_routes)} ({len(tier1_routes)/len(all_turns)*100:.1f}%)")
        print(f"Số lượt trúng Cache hoàn toàn (needs_retrieval = none): {len(cache_hits)}")
        print(f"Số lượt trúng Cache một phần (needs_retrieval = partial): {len(partial_hits)}")
        print(f"Số lượt phản hồi trực tiếp (Direct Answer): {len(direct_answers)}")
        print(f"Số lượt phát hiện lỗi mâu thuẫn sinh (Self-Check Failed): {len(self_check_failed)}")
        print(f"Số lượt lỗi Embedding (Embedding Failures): {len(embedding_failures)}")
        print(f"Số lượt câu trả lời độ tin cậy thấp (Low Confidence): {len(low_confidence_answers)}")
        print("
Phân rã phương thức định tuyến:")
        for method, count in method_counts.items():
            print(f"  - {method}: {count} ({count/len(all_turns)*100:.1f}%)")
        print(f"
Độ trễ phân vị p95 Latency: {p95_latency:.2f}ms")
        print(f"Độ trễ phân vị p99 Latency: {p99_latency:.2f}ms")
```
