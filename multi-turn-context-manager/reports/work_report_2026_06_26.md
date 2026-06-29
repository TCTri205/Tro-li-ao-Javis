# Báo cáo Kỹ thuật - Dự án Multi-Turn Context Manager
### Tài liệu Tổng hợp Công việc & Cải tiến Kiến trúc (Dành cho Tech Lead)

**Ngày báo cáo:** 26/06/2026  
**Người thực hiện:** TCTri (với sự hỗ trợ của Gemini CLI Agent)  
**Trạng thái:** 
* **V4 (Hallucination Hard Mode):** Hoàn thành ổn định hóa hệ thống, đạt tỷ lệ kiểm thử tuyệt đối **100.0% (16/16 kịch bản)**.
* **Cải tiến cấu trúc & di trú DB:** Triển khai cột `attributes` JSONB mới trong `session_entity_index`, viết migration script, và đồng bộ hóa logic ingestion.
* **Chuẩn hóa cấu hình:** Tham số hóa toàn bộ hệ thống (ngưỡng embedding, suffix lists giới tính, config circuit breaker, EMA caching) vào `src/config.py`.
* **V5 (Stress & Fuzzy Tests):** Thiết lập và hoàn thiện bộ suite kiểm thử V5 với tỉ lệ vượt qua **90.0% (9/10 kịch bản)**.

---

## 1. Tóm tắt kết quả (Executive Summary)

Hôm nay, công việc tập trung vào năm mảng cốt lõi nhằm ổn định và hoàn thiện hệ thống quản lý ngữ cảnh đa lượt:
1. **Ổn định hóa hệ thống V4 (V4 Stabilization):** Giải quyết triệt để lỗi hồi quy định tuyến "caller/receiver" trong kịch bản `H5_ROLE_REVERSAL_CHECK`. Đưa V4 test suite đạt tỷ lệ pass 100%.
2. **Nâng cấp Cơ sở dữ liệu (Database Migration & Ingestion):** Thêm cột `attributes` (JSONB) cho bảng `session_entity_index`. Sửa đổi script khởi tạo `init_db.py` và tạo script di trú `migrate_add_attributes_column.py`. Nâng cấp trích xuất thuộc tính cấu trúc trong `entity_extractor.py` để lưu trữ thông tin giới tính và công ty của thực thể.
3. **Chuẩn hóa & Tham số hóa Cấu hình (`config.py`):** Di chuyển các giá trị hardcoded của bộ lọc giới tính, các ngưỡng khoảng cách vector embedding (semantic gap, confindet match, topic shift), circuit breaker thresholds, EMA decay factors, và switch patterns từ `router.py` và `cache_manager.py` vào `src/config.py`.
4. **Cơ chế Chịu lỗi & Tối ưu hóa Router (`orchestrator.py` & `router.py`):** Triển khai cơ chế bọc try-except toàn bộ lệnh gọi Engine, tự động fallback từ SQL Engine sang RAG Engine khi gặp lỗi cú pháp hoặc timeout của SQL. Đồng thời vá lỗi kiểm tra `CACHE_TTL` cho Partial Fetch, chuẩn hóa fallback của WebEngine và loại bỏ mã chết trong router.
5. **Suite kiểm thử V5 (Stress & Fuzzy Match):** Viết tệp kiểm thử `test_suite_v5.py` tập trung vào nhiễu âm (Katakana, Romaji, viết tắt, homophones, typos STT) và phình to lịch sử hội thoại (LRU limit, recency check, switch-back).

---

## 2. Chi tiết các commit & Thay đổi kỹ thuật trong ngày

Dưới đây là thống kê chi tiết thay đổi kỹ thuật tương ứng với 8 commits đã được đẩy lên repository ngày hôm nay:

### a) Di trú CSDL & Trích xuất Thuộc tính Thực thể (P0 - DB Migration & Ingestion)
* **Commit:** `e560b0b - fix(v4-stabilization): fix caller/receiver routing regression in H5, resolve memory constraints, and achieve 100% test pass rate`
* **Thay đổi chính:**
  * Bổ sung script [migrate_add_attributes_column.py](file:///d:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/scripts/migrate_add_attributes_column.py) để chạy câu lệnh:
    ```sql
    ALTER TABLE session_entity_index ADD COLUMN attributes JSONB DEFAULT '{}'::jsonb;
    ```
  * Cập nhật [init_db.py](file:///d:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/scripts/init_db.py) để tự động tạo cột `attributes` cho các cài đặt mới.
  * Tinh chỉnh [entity_extractor.py](file:///d:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/src/entity_extractor.py) để bóc tách thông tin giới tính và công ty từ payload kết quả trả về của các Engine và nạp chúng vào DB chỉ mục dưới dạng JSONB.
  * Khắc phục lỗi `MemoryError` khi chạy trên môi trường Windows bằng cách giới hạn số luồng (threads = 1) cho các thư viện tính toán tuyến tính (OpenBLAS, MKL, OMP, v.v.) qua biến môi trường.

### b) Phòng chống Ảo giác & Cải tiến Cache (P1 - Hallucination Control)
* **Commit:** `59eed9e - fix(hallucination-control): patch cache TTL check in partial fetch, WebEngine fallback source naming, and remove unreachable router dead code`
* **Thay đổi chính:**
  * Sửa lỗi trong [cache_manager.py](file:///d:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/src/cache_manager.py): kiểm tra thời gian hết hạn (`CACHE_TTL`) của cache slot ngay cả trong kịch bản Partial Fetch, tự động hạ cấp xuống Full Retrieval nếu phát hiện dữ liệu cache đã hết hạn.
  * Chuẩn hóa đặt tên nguồn trả về khi WebEngine rơi vào nhánh fallback nhằm đảm bảo tính nhất quán dữ liệu cho Verifier.
  * Loại bỏ các phần mã chết (dead code) không thể tiếp cận trong [router.py](file:///d:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/src/router.py).

### c) Chuẩn hóa & Tham số hóa cấu hình (P2 - Config Centralization)
* **Commit:** `e560b0b` và `3612dbb - docs: add implementation plan for improvements (2026-06-26)`
* **Thay đổi chính:**
  * Xây dựng tệp [config.py](file:///d:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/src/config.py) chứa toàn bộ cấu hình hệ thống:
    * **Embedding thresholds:** `CONFIDENT_MATCH_DIST = 0.35`, `TOPIC_SHIFT_DIST = 0.55`, `SEMANTIC_GAP_RATIO = 0.65`.
    * **Gender filter suffix lists:** `male_suffixes` (32 hậu tố) và `female_suffixes` (27 hậu tố).
    * **Pronouns config:** Tách biệt danh sách đại từ đơn và đại từ số nhiều.
    * **Circuit Breaker config:** Cấu hình thời gian cooldown và ngưỡng lỗi tối đa.
    * **EMA cache vectors parameters:** Hệ số smoothing và điều chỉnh drift.

### d) Triển khai Test Suite V5 & Tinh chỉnh Logic Nhật Bản hóa (Japanese Prompts)
* **Commit:** 
  * `4765b4c - refactor: fix tier 2 chat history query ordering and add test suite v5`
  * `9aa94da - refactor: update router prompts for Japanese prompts/comparisons and add tests to suite V5`
* **Thay đổi chính:**
  * Viết lại câu lệnh SQL truy vấn lịch sử chat ở Tier 2 trong [router.py](file:///d:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/src/router.py), thay đổi sắp xếp từ `ORDER BY id ASC LIMIT 16` thành `ORDER BY id DESC LIMIT 16` (sau đó đảo ngược lại trong Python). Điều này sửa lỗi nghiêm trọng khi hệ thống bị phình to lịch sử hội thoại (lên tới 50 lượt), chỉ nhìn thấy các lượt chat cũ và bỏ qua các lượt chat mới nhất chứa bối cảnh quan trọng.
  * Nâng cấp prompts của Router để xử lý chính xác các đại từ so sánh và từ khóa liên quan của tiếng Nhật (ví dụ: "同氏", "両者", "双方", "同じ会社").
  * Thiết lập tệp [test_suite_v5.py](file:///d:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/tests/test_suite_v5.py) chứa 10 test cases phức tạp.

---

## 3. Kết quả Kiểm thử & KPIs hệ thống

Hệ thống đã chạy thành công V4 test suite với kết quả hoàn hảo. Kết quả tổng hợp của toàn bộ các phiên bản kiểm thử và các vấn đề tồn đọng kỹ thuật được chi tiết hóa dưới đây:

### Bảng kết quả kiểm thử các phiên bản (KPIs):

| Phiên bản kiểm thử | Trạng thái | Số lượng kiểm thử | Pass Rate | Lĩnh vực trọng tâm kiểm thử |
| :--- | :--- | :--- | :--- | :--- |
| **Test Suite V1** | Hoàn thành | 26 Turns | **100.0%** | Định tuyến luồng cơ bản (SQL/RAG/WEB) |
| **Test Suite V2** | Hoàn thành | 22 Turns | **90.9%** | Độ tin cậy Heuristics, chuyển tiếp Tier 2 |
| **Test Suite V3** | Hoàn thành | 31 Turns | **96.8%** | Phân giải đại từ mơ hồ, đồng bộ ngữ cảnh |
| **Test Suite V4** | Hoàn thành | 16 Scenarios | **100.0%** | Phòng chống ảo giác, kiểm soát hồi quy H5 |
| **Test Suite V5** | Đã triển khai | 10 Scenarios | **90.0%** | Phản ứng STT nhiễu âm & Phình to hội thoại |

### Vấn đề Tồn đọng (Blockers & Bugs) & Phân tích Chi tiết Lỗi:

#### 1. Bộ kiểm thử V2 (Độ tin cậy Heuristics)
* **Test Case thất bại:** `STD_TURN_4_SWITCHBACK`
  * **Lỗi ghi nhận:** Trả về kết quả trống hoặc thông báo không tìm thấy dữ liệu khi hỏi về thông tin giao dịch viên ngân hàng (GT_04).
  * **Nguyên nhân:** Lỗi phân giải thực thể khi switchback ngược về context cũ của session trước đó.
* **Test Case thất bại:** `NEG_016_SQL_FAILURE_FALLBACK`
  * **Lỗi ghi nhận:** Không kích hoạt thành công luồng xử lý dự phòng mong muốn khi truy vấn thực tế gặp lỗi DB/table không tồn tại.
  * **Nguyên nhân:** Heuristics chưa bắt trọn vẹn ngoại lệ lỗi SQL để hạ cấp định tuyến sang fallback phù hợp.

#### 2. Bộ kiểm thử V3 (Phân giải đại từ & Đồng bộ ngữ cảnh)
* **Test Case thất bại:** `G4_CONTEXT_POLLUTION_RECOVERY`
  * **Lỗi ghi nhận:** Không phục hồi thành công ngữ cảnh ban đầu của cuộc gọi GT_05 sau khi bị ô nhiễm bởi câu hỏi lạc đề (công thức mì ramen).
  * **Nguyên nhân:** EMA vector và cơ chế làm sạch cache chưa lọc hiệu quả nhiễu thông tin ngoài luồng.

#### 3. Bộ kiểm thử V5 (Stress & Fuzzy Match)
* **Test Case thất bại:** `B4_COMPOUND_PRONOUN_RESOLUTION`
  * **Lỗi ghi nhận:** `Compound resolution failed. Shimada resolved: False, Sato resolved: True, Retrieval: full`
  * **Nguyên nhân:** Khi người dùng hỏi: *"同氏と佐藤太郎さんは同じ会社に所属していますか？"* (Đồng chí đó và Sato Taro có thuộc cùng một công ty không?), bộ phân giải đại từ đã nhận diện chính xác "佐藤太郎" (Sato) nhưng chưa phân giải thành công đại từ ghép "同氏" (nguyên bản thuộc về Shimada trong ngữ cảnh trước đó) trong câu so sánh thực thể kép. Nhánh xử lý này đã kích hoạt Full Retrieval nhưng chưa liên kết đúng Shimada vào cấu trúc thực thể.

---

## 4. Kế hoạch tiếp theo (Action Items)

Dựa trên tài liệu [implementation_plan_2026_06_26.md](file:///d:/VJ/Tro-li-ao-Javis/multi-turn-context-manager/docs/implementation_plan_2026_06_26.md), kế hoạch trong các phiên làm việc tiếp theo bao gồm:

1. **[P0] Sửa lỗi Case B4 trong V5:** Tinh chỉnh prompt viết lại câu hỏi (Query Rewriter) của Router Tier 2 để xử lý chính xác đại từ ghép tiếng Nhật ("同氏") khi so sánh nhiều thực thể cùng lúc.
2. **[P1] Tránh Overfitting & Tích hợp mô hình thật:** Tiến hành kiểm thử hệ thống với mô hình nhúng thực tế (ví dụ: `multilingual-e5-small`) thay vì `MockSentenceTransformer` để tinh chỉnh lại các ngưỡng động thực tế.
3. **[P2] Giám sát Verifier:** Triển khai bảng theo dõi số lần retry và tỷ lệ tự phát hiện ảo giác của hàm `_verify_hallucination` trên môi trường giám sát tập trung.
4. **[P2] Thay thế Web Search Simulator:** Tích hợp API thật của Tavily hoặc Google Search để kiểm thử khả năng tìm kiếm thông tin thời gian thực.

---
*Báo cáo được hoàn thiện và xác thực tự động bởi Javis AI CLI.*
