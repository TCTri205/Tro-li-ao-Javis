# Kế hoạch Cải tiến & Nâng cấp Hệ thống Multi-Turn Context Manager
**Ngày cập nhật:** 26/06/2026
**Trạng thái:** Đã phân tích, Đối chiếu & Hoàn thiện — Cập nhật dựa trên rà soát codebase thực tế

Tài liệu này trình bày kế hoạch cải tiến và nâng cấp hệ thống quản lý ngữ cảnh đa lượt Javis lên chuẩn vận hành thực tế (Production). Mục tiêu cốt lõi của kế hoạch là triệt tiêu các thuật toán Heuristics cứng nhắc, khắc phục hiện tượng Overfitting kỹ thuật, nâng cao khả năng chịu lỗi và tối ưu hóa sâu khả năng xử lý tiếng Nhật cho các truy vấn của người dùng.

---

## Lộ trình Triển khai & Thứ tự Ưu tiên (Roadmap)

Để đảm bảo hệ thống vận hành liên tục và không bị gián đoạn, các nhiệm vụ được phân cấp và thực hiện theo thứ tự sau:
1. **[P0]** Thay đổi Schema DB & Migration (Mục 6) — Phải thực hiện đầu tiên để chuẩn bị hạ tầng lưu trữ.
2. **[P0]** Lọc sạch chỉ mục thực thể ở cả SQL & RAG (Mục 3) và Nâng cấp Cơ chế Fallback SQL → RAG khi có Exception (Mục 4).
3. **[P1]** Cập nhật Logic Định tuyến & Phân giải Thực thể (Mục 2) bao gồm lưu Gender vào Metadata JSONB.
4. **[P2]** Chuẩn hóa cấu hình hệ thống (Mục 1) di chuyển toàn bộ tham số cứng vào `config.py`.
5. **[P2]** Siết chặt bộ dịch SQL Heuristic (Mục 5).
6. **[P3]** Triển khai Giám sát (Mục 8) & Kịch bản Kiểm chứng (Mục 7).

---

## 1. Chuẩn hóa Cấu hình Hệ thống (`config.py`)

*   **Tham số hóa Ngưỡng Embedding:** Đưa toàn bộ các giá trị ngưỡng so sánh khoảng cách vector tĩnh vào cấu hình hệ thống dưới dạng các hằng số. Các tham số này hiện đang hardcoded trong `router.py` (dòng 1190 và 1203) và `cache_manager.py` (hàm `update_cache_slot_ema`), bao gồm:
    *   Ngưỡng tối đa để xác nhận một trận khớp ngữ nghĩa tự tin (Confident Semantic Match): `d1 < 0.35` (dòng 1190).
    *   Ngưỡng tối thiểu để cảnh báo hiện tượng chuyển đổi chủ đề cuộc thoại (Semantic Shift): `d1 > 0.55` (dòng 1203).
    *   Tỷ lệ giới hạn khoảng cách giữa thực thể gần nhất và thực thể gần thứ hai để đánh giá mức độ mơ hồ của câu hỏi (Semantic Gap Ratio Limit): `gap < 0.65` (dòng 1190).
*   **Tham số hóa Bộ lọc Giới tính:** Di chuyển toàn bộ danh sách các hậu tố tiếng Nhật dùng để phân loại giới tính từ bộ định tuyến vào tệp cấu hình chính dưới dạng từ điển ánh xạ giới tính để phục vụ cho các phương án xử lý dự phòng. Các danh sách này hiện đang hardcoded trong method `route()` của `router.py` (khoảng dòng 605-615):
    *   `female_suffixes`: **27** hậu tố (子, 美, 香, 花, 華, 奈, 菜, 乃, 莉, 里, 理, 梨, 咲, 織, 恵, 絵, 江, 穂, 沙, 紗, 羽, 和, 音, 凛, 杏, 楓, 葵)
    *   `male_suffixes`: **32** hậu tố (郎, 朗, 夫, 男, 雄, 介, 助, 佑, 佐, 人, 斗, 翔, 登, 太, 也, 哉, 弥, 樹, 輝, 木, 司, 嗣, 馬, 吾, 悟, 将, 正, 雅, 洋, 博, 宏, 浩)
*   **Tham số hóa Danh sách Đại từ `PRONOUNS`:** Di chuyển danh sách đại từ cứng hiện đang khai báo trong `router.py` (dòng 22-36) vào `config.py`.
*   **[BỔ SUNG] Tham số hóa Danh sách Đại từ Số ít `singular_pronouns`:** Di chuyển danh sách đại từ dùng để resolve singular pronouns tại `router.py` (dòng 517) `["彼", "彼女", "それ", "その人", "先ほどの担当者", "先ほどの", "その件", "その話"]` vào `config.py`.
*   **Tham số hóa Bản đồ Ánh xạ Loại Entity (Entity Type Mapping):** Đưa bản đồ ánh xạ chuyển đổi các loại thực thể thô (như `company`, `organization`, `location`, `user`,...) về các định dạng loại chuẩn được hệ thống chấp nhận (`person`, `document`,...) từ `entity_extractor.py` (dòng 279-292) vào `config.py`.
*   **Tham số hóa Cấu hình Circuit Breaker:** Đưa các thông số của bộ ngắt mạch tự động trong `engines.py` vào `config.py` để quản lý tập trung. Hiện đang hardcoded trong `EngineCircuitBreaker.__init__` (dòng 25):
    *   `failure_threshold = 3` (số lần lỗi tối đa)
    *   `cooldown_seconds = 30` (thời gian tạm dừng kết nối)
    *   `timeout_seconds = 30.0` (thời gian chờ tối đa mặc định của class, thực tế đang được override thành `60.0` khi khởi tạo trong `orchestrator.py` dòng 165-167).
*   **Tham số hóa Trí nhớ Thực thể (Entity Memory Decay):** Đưa các hệ số suy hao độ nóng (Decay Factor) của thực thể (hiện đang nhân cố định với 0.5 tại dòng 259) và lượng tăng độ nóng (Increment) của thực thể (hiện đang cộng cố định 1.0 tại dòng 252) trong hàm `update_entity_interaction_counts()` của `router.py` vào `config.py`.
*   **Tham số hóa EMA (Exponential Moving Average) của Cache Embedding:** Hàm `update_cache_slot_ema()` trong `cache_manager.py` (dòng 191-311) có các tham số hardcoded cần đưa vào config:
    *   `alpha = 0.8` (hệ số EMA làm mượt vector embedding).
    *   `max_update_count = 5` (giới hạn số lần cập nhật EMA, sau đó vector bị khóa).
    *   `cos_distance_threshold = 0.5` (ngưỡng khoảng cách cosine để bypass cập nhật EMA).
    *   `similarity_safeguard = 0.60` (ngưỡng tương đồng tối thiểu với vector gốc để tránh drift quá xa).
*   **Tham số hóa Switch Keywords Pattern:** Hardcoded regex trong `router.py` (dòng 19):
    *   `SWITCH_KEYWORDS_PATTERN = re.compile(r'(やっぱり|別の話|キャンセル|スキップ|忘れて)', re.IGNORECASE)` — dùng để phát hiện chuyển chủ đề cứng ở Tier 1.
*   **Tham số hóa và Tối ưu hóa Đường dẫn Trả lời Trực tiếp (Direct-Answer Path):**
    *   Đưa các danh sách từ khóa tiếng Nhật trong `should_use_direct_path()` (ở `orchestrator.py`) và `config.py` (ví dụ: các từ khóa về suy luận logic như `理由`, `背景`, `なぜ`,... và từ khóa về vai trò như `誰から`, `誰に`, `発信`,...) vào tệp cấu hình chính để quản lý tập trung và tránh hardcode logic.
*   **[BỔ SUNG] Tham số hóa `get_adaptive_max_tokens`:** Đưa các hằng số token giới hạn (1500 cho reasoning models, 300 cho chat models, 800 default) trong `config.py` (dòng 66-80) thành các tham số cấu hình rõ ràng.

---

## 2. Nâng cấp Logic Định tuyến & Phân giải Thực thể (`router.py`)

*   **Động hóa Phân tích Khoảng cách Ngữ nghĩa:** Thay thế việc so khớp cứng các khoảng cách vector bằng cách đối chiếu với các tham số ngưỡng động từ cấu hình hệ thống. Các trường hợp rơi vào vùng xám (mơ hồ giữa hai thực thể) sẽ được đẩy trực tiếp lên Lớp xử lý thứ hai (Tier 2) thay vì tự ý đưa ra phán quyết thiếu chính xác ở Lớp thứ nhất (Tier 1).
*   **Phân giải Giới tính dựa trên Dữ liệu Cấu trúc:**
    *   Code hiện tại thực hiện: truy vấn `transcripts.participants` JSONB trước, xây `female_names`/`male_names` sets từ DB, sau đó mới fallback sang suffix matching.
    *   **Cải tiến cốt lõi:** Lưu trữ kết quả phân giải giới tính thu được từ DB hoặc suffix matching vào cột metadata JSONB mới của bảng `session_entity_index` (xem mục 6) để tránh việc phải liên tục truy vấn lại bảng transcripts khi xử lý đại từ nhân xưng.
*   **[BỔ SUNG] Tham số hóa và Tài liệu hóa Gender Substring Propagation:** Rà soát và chuyển đổi cơ chế so khớp substring tên (dòng 628-654) thành một bộ rule mềm dẻo hơn hoặc tham số hóa phần check trùng lặp tên.
*   **Chuyển giao Tuyệt đối Đại từ Số nhiều:**
    *   Di chuyển `plural_pattern = re.compile(r'(彼ら|彼女ら|ら\b|方々|お二人|二人|双方|両者)')` vào `config.py`.
    *   Đảm bảo Tier 2 viết lại chính xác plural pronouns khi xử lý các thực thể nằm ở các session khác nhau (cross-session entities) - ví dụ: "彼ら" khi đang nói về GT_04 và GT_02.
*   **Ràng buộc Động cho Đại từ Chung:** Loại bỏ hoàn toàn cơ chế đối sánh cứng các danh từ chung chung trong Cơ sở Dữ liệu chỉ mục. Router sẽ tự động phân giải các từ này về thực thể đang hoạt động gần nhất dựa trên thông tin vị trí bộ nhớ đệm (Cache Slot) đang được tải.

---

## 3. Trích xuất Thực thể & Quản lý Chỉ mục (`entity_extractor.py`)

*   **Lọc Sạch Chỉ mục Thực thể:** Triển khai một bộ lọc hậu xử lý sau bước trích xuất bằng LLM. Bộ lọc này sẽ chủ động loại bỏ toàn bộ các đại từ chung hoặc danh từ trừu tượng ra khỏi danh sách tên hiển thị của thực thể. 
    *   **Lưu ý quan trọng:** Việc lọc sạch display names chung chung như "その通話", "先ほどの通話", "さっき của 通話" phải được áp dụng đồng thời cho **cả SQL pipeline** (dòng 58-79) và **RAG pipeline** (dòng 161-182) để tránh trùng lặp mã nguồn và lọt dữ liệu rác.
*   **Trích xuất Thuộc tính Cấu trúc:** Nâng cấp hàm xử lý để bóc tách thông tin giới tính và công ty từ kết quả trả về của các Engine (SQL/RAG). Dữ liệu này sẽ được cấu trúc hóa và đóng gói thành siêu dữ liệu (Metadata) dưới dạng JSON để lưu trữ vào cột `attributes` JSONB mới trong `session_entity_index`.
*   **Động hóa Phiên bản Mô hình Embedding (Dynamic Embedding Versioning):** Loại bỏ việc ghi cứng tên mô hình nhúng `'multilingual-e5-small'` khi ghi nhận bộ nhớ đệm (Cache Slot) trong hàm `insert_cache_slot()` (dòng 74) của `cache_manager.py`. Thay vào đó, tên phiên bản mô hình sẽ được nạp động từ cấu hình `config.py` hoặc trích xuất trực tiếp từ siêu dữ liệu của đối tượng mô hình nhúng đang hoạt động (`SentenceTransformer`).
*   **[BỔ SUNG] Bảo toàn logic GT Scoping trong RAG:** Giữ nguyên và tối ưu hóa logic lọc thực thể theo GT session trong RAG pipeline (dòng 150-159): nếu entity GT không khớp với `query_gts` đang xét thì bỏ qua hoàn toàn để tránh cross-session pollution.

---

## 4. Tối ưu hóa Điều phối & Cơ chế Chịu lỗi (`orchestrator.py`)

*   **Cơ chế Chịu lỗi Đa tầng (Robust Fallback):**
    *   **Bổ sung xử lý Ngoại lệ:** Bao bọc toàn bộ các lệnh gọi thực thi Engine trong các khối xử lý ngoại lệ (`try-except`). Nếu `SQLEngine` gặp sự cố (lỗi cú pháp SQL, timeout, hoặc exception hệ thống), hệ thống sẽ tự động bắt ngoại lệ này và chuyển hướng yêu cầu sang `RAGEngine` thay vì chỉ fallback khi trả về tập kết quả rỗng (`not payload.get("rows")`) như hiện tại.
    *   Trong tình huống nghiêm trọng nhất khi cả hai Engine dữ liệu đều gặp lỗi, Orchestrator sẽ kích hoạt mức dự phòng cuối cùng: chuyển yêu cầu sang chế độ xử lý bằng tri thức nội tại của mô hình ngôn ngữ lớn (Parametric Knowledge) thay vì dừng hoạt động hệ thống.
*   **[BỔ SUNG] Quản lý Concurrent Lock trong Cache:** Khi thực hiện refactor `update_cache_slot` (ở `cache_manager.py` dòng 124-173), **bắt buộc phải giữ nguyên cơ chế khóa `SELECT ... FOR UPDATE`** (dòng 132-136) để tránh tranh chấp dữ liệu (race condition) khi thực hiện LRU eviction đồng thời.

---

## 5. Ràng buộc Heuristics cho các Công cụ Truy vấn (`engines.py`)

*   **Siết chặt Bộ dịch SQL Heuristic:** Loại bỏ toàn bộ các từ khóa liên quan đến hành động hoặc mối quan hệ phức tạp ra khỏi danh sách dịch trực tiếp của SQL Heuristic. Nhóm từ khóa `HEURISTIC_SQL_DETAIL` (định nghĩa ở `config.py` dòng 17-19 bao gồm "詳細", "具体の内容", "話したこと", "内容", "中身", "伝言", "発言",...) cần được loại bỏ khỏi heuristic translation và chuyển hoàn toàn qua luồng biên dịch đầy đủ của LLM hoặc RAGEngine để bảo toàn ngữ cảnh phong phú của cuộc gọi.
*   **Giới hạn Phạm vi Hoạt động:** Quy định bộ dịch SQL Heuristic chỉ được phép áp dụng cho các truy vấn siêu dữ liệu thuần túy về mặt số lượng (DURATION, MEMBERS) hoặc thời gian.
*   **Bảo toàn Guards hiện có:** Giữ lại các logic guards đang chạy ổn định:
    *   Range query guard: từ chối heuristic nếu query chứa `"から" ... "まで"`, `"の間"`, `"期間"`.
    *   GT range guard: từ chối heuristic nếu query chứa `GT_01からGT_09` hoặc `GT_01〜GT_09`.

---

## 6. Thay đổi Cấu trúc Cơ sở Dữ liệu & Di trú Dữ liệu

*   **Nâng cấp Bảng Chỉ mục Thực thể:** Bổ sung thêm một cột lưu trữ siêu dữ liệu bán cấu trúc (kiểu dữ liệu JSONB) vào bảng `session_entity_index`. Cột mới sẽ lưu trữ linh hoạt các thuộc tính trích xuất được (như giới tính, tổ chức, chức danh) của từng thực thể mà không cần phải thay đổi cấu trúc bảng trong tương lai khi có yêu cầu mới.
*   **Quy trình Di trú Dữ liệu (Data Migration - Bắt buộc chạy P0):**
    *   Thực hiện câu lệnh `ALTER TABLE session_entity_index ADD COLUMN attributes JSONB DEFAULT '{}'::jsonb;` để bổ sung cột siêu dữ liệu mới vào cơ sở dữ liệu hiện tại trước khi triển khai mã nguồn mới.
    *   Cập nhật tập lệnh khởi tạo cơ sở dữ liệu gốc (`init_db.py`) để đảm bảo các môi trường triển khai mới sau này sẽ tự động tạo bảng đúng cấu trúc chuẩn hóa.
    *   Cung cấp giá trị mặc định `'{}'::jsonb` cho cột siêu dữ liệu đối với toàn bộ các bản ghi cũ để đảm bảo tính tương thích ngược hoàn toàn.

---

## 7. Kịch bản & Kế hoạch Kiểm chứng (Verification Plan)

*   **Kiểm thử Tích hợp với Mô hình Embedding Thực tế:**
    *   Thay thế bộ nhúng giả lập (Mock) bằng một mô hình nhúng thực tế có kích thước nhỏ gọn trong quá trình chạy thử nghiệm để kiểm tra chính xác khả năng phân tích khoảng cách ngữ nghĩa và nhận diện chuyển đổi chủ đề.
    *   **Lưu ý quan trọng về cách chạy:** Thực hiện chạy kịch bản kiểm thử trực tiếp thông qua trình thông dịch Python với tệp kịch bản kiểm thử số 4 (không sử dụng lệnh chạy của khung kiểm thử pytest vì tệp kịch bản được viết dưới dạng mã nguồn chạy tuần tự trực tiếp).
*   **Kiểm thử Phân giải Thực thể nâng cao:**
    *   **Đã có:** V4 H10 test gender-aware pronoun resolution (彼→佐藤太郎, 彼女→鈴木花子). V4 H3 test double pronoun replacement (彼+それ→島田+物件). V3 D1-D3 test entity disambiguation.
    *   **Cần bổ sung:** Test tích hợp việc ghi nhận/đọc gender từ cột metadata `attributes` của entity index. Test cho việc Tier 2 rewrite plural pronouns với cross-session entities.
*   **Kiểm tra direct path với `is_verifier_mocked`:** Kiểm tra và đảm bảo khi verifier bị mock (`is_verifier_mocked=True` truyền vào từ `should_use_direct_path`), direct path hoạt động đúng hành vi thiết kế và không bỏ lọt các lỗi hallucination.

---

## 8. Giám sát & Quản lý Lỗi Vận hành (Operational Monitoring)

*   **Ghi nhận Nhật ký lỗi Tập trung:** Bên cạnh việc ghi nhận nhật ký lỗi ra tệp cục bộ bằng thư viện Python `logging`, hệ thống cần được cấu hình để đẩy các lỗi nghiêm trọng về dịch vụ giám sát tập trung trên môi trường Production.
*   **Các sự kiện bắt buộc giám sát:**
    *   Sự kiện ngắt mạch (Circuit Breaker) bị kích hoạt ở bất kỳ Engine nào.
    *   Các sự cố mất kết nối hoặc hết thời gian chờ (Timeout) với cơ sở dữ liệu PostgreSQL.
    *   Tần suất hệ thống phải kích hoạt chế độ dự phòng cuối cùng (Parametric Knowledge).
    *   **[BỔ SUNG] Giám sát kết quả Tự kiểm tra Hallucination:** Theo dõi tần suất retry và tỷ lệ tự phát hiện hallucination của hàm `_verify_hallucination` (orchestrator.py dòng 671-715) cùng mức độ tự tin phân loại (`high`/`medium`/`low`).
