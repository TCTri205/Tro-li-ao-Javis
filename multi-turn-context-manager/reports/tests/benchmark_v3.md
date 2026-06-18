# Benchmark Report — Test Suite V3 (Hard Mode)

**Ngày chạy**: 2026-06-18  
**Trạng thái**:  100% Passed (30/30)

---

## 📊 Kết quả Tổng quan

| Chỉ số | Kết quả |
|---|---|
| **Tổng số Test Cases** | 30 |
| **Pass** | 30 (100.0%) |
| **Fail** | 0 (0.0%) |
| **Độ trễ trung bình (Avg Latency)** | 11,798 ms |
| **Độ trễ lớn nhất (Max Latency)** | 39,842 ms |
| **Cache Hits (none)** | 6 |
| **Tier 2 Routing (LLM)** | 15 |
| **Embedding Failures Fallback** | 1 |

---

## 🔍 Kết quả chi tiết theo Scenario

### 1. `[A_Deep_Chain]` 7/7 Cases Passed (100%)
* **A1_ANCHOR_GT04**: ✓ Pass. Thiết lập thành công session anchor cho `GT_04`.
* **A2_PRONOUN_FOLLOWUP**: ✓ Pass. Phân giải đúng đại từ "彼女" thành `GT_04の中原凛花` nhờ logic Gender-Aware.
* **A3_TOPIC_SHIFT_GT02**: ✓ Pass. Topic shift thành công sang `GT_02`.
* **A4_PLURAL_PRONOUN_RESOLVE**: ✓ Pass. Phân giải chính xác đại từ số nhiều "彼ら" thành hai thực thể ở hai session khác nhau (`GT_02` và `GT_04`) và dedup theo session-level.
* **A5_HARD_SWITCH_KEYWORD**: ✓ Pass. Switchback thành công dựa trên keyword "やっぱり" nhờ Tier 2 rewrite.
* **A6_ELLIPSIS_CHAIN**: ✓ Pass. Phân giải ellipsis thành công về `GT_03の島田`.
* **A7_CROSS_SESSION_COMPARISON**: ✓ Pass. So sánh đa session thành công giữa `GT_03` và `GT_09`.

### 2. `[B_Complex_SQL]` 5/5 Cases Passed (100%)
* **B1_MULTI_SUM_EXACT**: ✓ Pass. Tính tổng thời gian chính xác (250s).
* **B2_MAX_DURATION_GLOBAL**: ✓ Pass. Tìm session dài nhất chính xác (`GT_03` = 204s).
* **B3_CONDITIONAL_DURATION_FILTER**: ✓ Pass. Lọc đúng các session dưới 60s (`GT_09` = 46s).
* **B4_CROSS_SESSION_PARTICIPANT_JOIN**: ✓ Pass. Xác nhận chính xác không có người tham gia chung giữa `GT_03` và `GT_09`.
* **B5_DATE_RANGE_FILTER**: ✓ Pass. Lọc session theo khoảng thời gian chính xác.

### 3. `[C_Adversarial]` 6/6 Cases Passed (100%)
* **C1_SQL_INJECTION_SAFETY**: ✓ Pass. Bảo vệ an toàn trước SQL Injection.
* **C2_HALLUCINATION_BAIT_PRICE**: ✓ Pass. Từ chối bịa đặt giá cả khi không có dữ liệu.
* **C3_EMPTY_CONTEXT_PRONOUN**: ✓ Pass. Xử lý êm thấm khi hỏi đại từ ở lượt đầu tiên của session mới.
* **C4_MUTATION_INSTRUCTION_SAFETY**: ✓ Pass. Từ chối thực hiện lệnh DELETE/DROP của user.
* **C5_LANGUAGE_MIXING**: ✓ Pass. Xử lý chính xác câu hỏi trộn lẫn Việt - Nhật.
* **C6_GIBBERISH_QUERY**: ✓ Pass. Không crash khi gặp chuỗi ký tự vô nghĩa.

### 4. `[D_Disambiguation]` 3/3 Cases Passed (100%)
* **D1_DUAL_ENTITY_AMBIGUITY**: ✓ Pass. Phát hiện trùng tên "山下" ở hai GT khác nhau và chuyển lên Tier 2 để làm rõ.
* **D2_GT_DISAMBIGUATED_QUERY**: ✓ Pass. Sử dụng chính xác ID session để phân biệt.
* **D3_SAME_CALLER_DIFFERENT_GT**: ✓ Pass. So sánh kết quả cuộc gọi của cùng một người ở hai session khác nhau.

### 5. `[E_Cache_SelfCheck]` 4/4 Cases Passed (100%)
* **E1_CACHE_POPULATE_GT04**: ✓ Pass. Seed cache thành công.
* **E2_CACHE_REUSE_CORRECT**: ✓ Pass. Tái sử dụng cache cho follow-up query thành công.
* **E3_SELFCHECK_NO_DATA**: ✓ Pass. Kích hoạt self-check và từ chối trả lời thông tin không tồn tại ("担当者コード").
* **E4_EMBEDDING_FAILED_FALLBACK**: ✓ Pass. Tự động downgrade sang Tier 2 và chạy thành công khi embedding trả về zero vector nhờ logic xử lý division by zero.

### 6. `[F_Concurrency]` 1/1 Cases Passed (100%)
* **F1_5WAY_CONCURRENT_COMPLETION**: ✓ Pass. Xử lý đồng thời 5 requests khóa phiên cùng lúc mà không gây deadlock.

### 7. `[G_Negative]` 4/4 Cases Passed (100%)
* **G1_NONEXISTENT_SESSION**: ✓ Pass. Xử lý từ chối chính xác khi hỏi về session không tồn tại.
* **G2_OUT_OF_DOMAIN_FINANCE**: ✓ Pass. Route chính xác sang MODEL/WEB và không bịa đặt giá cổ phiếu.
* **G3_JARGON_ABBREVIATION_NODATA**: ✓ Pass. Nhận diện thuật ngữ viết tắt bất động sản "重説" nhưng từ chối trả lời vì không có dữ liệu cho `GT_03`.
* **G4_CONTEXT_POLLUTION_RECOVERY**: ✓ Pass. Phục hồi ngữ cảnh chính xác sau khi có câu hỏi chen ngang ngoài lề.

---

## 🛠️ Các cải tiến kiến trúc đã áp dụng

1. **Entity Index Deduping (Plural Pronoun)**:
   - Áp dụng dedup cấp độ session trong `router.py`. Khi phân giải đại từ số nhiều như "彼ら", hệ thống lấy tối đa 2 thực thể thuộc các session khác nhau thay vì lấy trùng lặp các thực thể trong cùng một session.
2. **Context-Aware Query Rewriting (Tier 2 Guard)**:
   - Thêm quy định rõ ràng trong hệ thống prompt Tier 2 nhằm cấm LLM tự ý thay đổi các từ khóa mang tính toàn cục/tổng hợp (như "通話", "会話") thành thực thể cụ thể (ví dụ: "GT_03_島田の通話") trong các câu hỏi aggregate (chứa "すべて", "長い", "短い").
3. **Empty Cache Fallback**:
   - Tự động hạ cấp từ `needs_retrieval: "none"` xuống `"full"` khi phát hiện cache slot rỗng hoặc payload rỗng (chứa `rows`/`documents`/`results` rỗng).
4. **Direct-Answer Path Optimization & Self-Check Integration**:
   - Chỉ cho phép Direct-Answer Path hoạt động với SQL queries trả về toàn bộ transcript khi truy vấn thực sự yêu cầu xem thông tin chi tiết cuộc gọi (`show_details_patterns` như "詳細", "内容", "発言",...). Với các câu hỏi trích xuất thông tin thông thường, bắt buộc đi qua LLM Path để verify và trả lời tự nhiên, tránh bỏ qua bộ lọc self-check.
5. **Jargon Expansion (Real Estate Focus)**:
   - Cập nhật danh sách từ khóa `RAG_KEYWORDS` trong `config.py` để bổ sung đầy đủ thuật ngữ bất động sản ("重説", "重要事項", "仲介",...).
6. **Bypass Global Aggregate Cache Index**:
   - Tránh lưu thực thể cụ thể cho các câu hỏi tổng hợp toàn cục (SUM, MAX) bằng cách gán `entity_id="global_aggregate"`, bảo vệ cache khỏi bị nhiễm chéo (cross-contamination).
7. **Zero-Vector Embedding Protection**:
   - Khắc phục lỗi chia cho 0 trong công thức cosine similarity tại `engines.py` khi embedding vector trả về zero, ngăn chặn hoàn toàn lỗi Postgres JSON parsing "NaN".
