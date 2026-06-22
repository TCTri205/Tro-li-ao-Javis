# Báo cáo Đánh giá Production Readiness & Giải pháp chống Overfitting
## Dự án: Multi-Turn Context Manager

---

## 1. Giới thiệu chung
Hệ thống **Multi-Turn Context Manager** đã vượt qua cả 3 phiên bản Test Suite (V1, V2, V3) với tỷ lệ chính xác tuyệt đối (30/30 kịch bản ở V3 Hard Mode). Tuy nhiên, các bộ kiểm thử này sử dụng tập dữ liệu giả lập (Domain Bất động sản và các cuộc gọi từ GT_01 đến GT_09) cùng các mô hình mock (như `MockSentenceTransformer`). 

Bản báo cáo này tổng hợp chi tiết các điểm **Overfitting kỹ thuật** và **Heuristics cứng (Brittle logic)** hiện tại trong hệ thống, đồng thời đề xuất **Giải pháp tối ưu hóa** nhằm đảm bảo hệ thống có thể tổng quát hóa và hoạt động chính xác trên môi trường Production thực tế với dữ liệu ngoài miền (out-of-domain) và mô hình thật.

---

## 2. Phân tích chi tiết & Giải pháp cải tiến tối ưu

### Vấn đề 1: Ngưỡng khoảng cách Vector cứng (`dist < 0.22` và `dist > 0.55`)
*   **Hiện trạng kỹ thuật (`src/router.py`):** Phân luồng nhanh ở Tier 1 dựa trên khoảng cách Cosine tuyệt đối: `dist < 0.22` định danh là cùng chủ đề (`same_topic`/`same_entity`) và `dist > 0.55` xác định đổi chủ đề (`topic_shift`).
*   **Rủi ro trên Production:** Các ngưỡng này được tinh chỉnh cho `MockSentenceTransformer` (sinh vector ngẫu nhiên có tính trực giao cao). Đối với các mô hình Embedding thực tế (như `multilingual-e5-small`), khoảng cách Cosine giữa các câu trong cùng một ngôn ngữ thường rất hẹp (similarity nền > 0.75, khoảng cách < 0.25). Ngưỡng đổi chủ đề `dist > 0.55` sẽ không bao giờ được kích hoạt, gây lỗi kẹt ngữ cảnh (luôn tái sử dụng context cũ dù người dùng đã đổi chủ đề).
*   **Giải pháp tối ưu (Semantic Gap Analysis):**
    1.  **Tính khoảng cách tương đối:** So sánh khoảng cách của Slot gần nhất ($d_1$) với Slot gần thứ hai ($d_2$). Nếu tỉ lệ $d_1 / d_2 < 0.65$ và $d_1 < 0.35$ (đối với mô hình thật), hệ thống tự tin phân loại vào cùng chủ đề.
    2.  **Phân luồng vùng xám lên Tier 2:** Nếu khoảng cách nằm ở vùng trung gian không rõ ràng, chuyển giao quyền quyết định cho LLM ở Tier 2 dựa trên lịch sử hội thoại thay vì dùng heuristics đoán tuyệt đối.

### Vấn đề 2: Giải thuật phân giải giới tính bằng hậu tố tên (Suffix Kanji)
*   **Hiện trạng kỹ thuật (`src/router.py` - dòng 538-560):** Phân biệt giới tính để giải nghĩa "彼" (anh ấy) và "彼女" (cô ấy) bằng cách khớp hậu tố Kanji cuối cùng của tên người tham gia (ví dụ: "子", "美", "郎", "雄").
*   **Rủi ro trên Production:** 
    1.  Trong đàm thoại doanh nghiệp B2B thực tế, đối tác xưng hô 100% bằng **họ (Last Name) + さん** (như `佐藤さん`, `中岡さん`, `島田さん`), không chứa hậu tố giới tính.
    2.  Thuật toán thất bại hoàn toàn với tên Hiragana, Katakana hoặc tên nước ngoài (như `John`, `Mary`). Khi có từ 2 thực thể không rõ giới tính hoạt động, hệ thống rơi vào nhánh fallback lấy người đầu tiên trong mảng, gây phân giải sai lệch giới tính.
*   **Giải pháp tối ưu (Ingestion Metadata & JSONB Schema):**
    1.  **Cấu trúc dữ liệu Ingestion:** Chuyển đổi cột `participants` trong bảng `transcripts` từ dạng mảng chuỗi đơn giản sang định dạng JSONB để lưu trữ thông tin cấu trúc dạng:
        ```json
        [
          {"name": "中岡", "gender": "male", "company": "Valtes"},
          {"name": "石田", "gender": "female", "company": "Unknown"}
        ]
        ```
    2.  **Đồng bộ chỉ mục:** Lưu thông tin giới tính này vào bảng `session_entity_index` khi nạp cuộc gọi để Router Tier 1 truy vấn trực tiếp.
    3.  **Fallback lên Tier 2:** Nếu thông tin giới tính bị thiếu hoặc có tranh chấp giữa các thực thể, chuyển hướng yêu cầu lên Tier 2 để LLM xử lý dựa trên ngữ cảnh hội thoại.

### Vấn đề 3: Tránh trùng lặp session số nhiều cho "彼ら" (`seen_sessions`)
*   **Hiện trạng kỹ thuật (`src/router.py` - dòng 388-395):** Khi phân giải đại từ số nhiều như "彼ら", "お二人", hệ thống lọc loại bỏ các thực thể thuộc cùng một session (`ent_session not in seen_sessions`).
*   **Rủi ro trên Production:** Logic này bị overfit cho Test Case A4 (so sánh GT_02 và GT_04). Trong thực tế, đại từ số nhiều phần lớn dùng để chỉ **các bên tham gia trong cùng một cuộc gọi hiện tại** (như "お二人の会話の要点" - tóm tắt cuộc đối thoại của hai người). Bộ lọc cứng này sẽ khiến hệ thống không thể tìm đúng thực thể trong cùng một phiên, gây lỗi ngữ nghĩa nghiêm trọng.
*   **Giải pháp tối ưu (Bypass đại từ số nhiều lên Tier 2):**
    1.  **Đơn giản hóa Tier 1:** Chỉ phân giải đại từ đơn lẻ, rõ ràng, ánh xạ 1-1 (như "彼", "彼女", "それ") ở Tier 1.
    2.  **Chuyển giao đại từ số nhiều cho Tier 2:** Các đại từ số nhiều ("彼ら", "お二人", "両者", "双方") mang tính trừu tượng và phụ thuộc nặng vào ngữ cảnh. Chuyển thẳng các yêu cầu này lên LLM ở Tier 2 để viết lại câu truy vấn (Query Rewriter) một cách chính xác tuyệt đối.

### Vấn đề 4: Trình biên dịch SQL Heuristics (`heuristic_sql_translation`)
*   **Hiện trạng kỹ thuật (`src/engines.py` - dòng 89-141):** Tự động dịch sang SQL bằng Regex khi phát hiện các từ khóa thuộc nhóm `HEURISTIC_SQL_MEMBERS` (như "誰", "名前", "相手") nhằm tối ưu tốc độ.
*   **Rủi ro trên Production:** Nếu câu hỏi chứa từ khóa "相手" nhưng đối tượng cần tìm là một người được nhắc đến gián tiếp trong cuộc gọi (như "石田志保" trong GT_02) chứ không phải là người tham gia trực tiếp cuộc gọi, họ sẽ không có tên trong cột `participants`. Do heuristics phân luồng trực tiếp vào SQL Engine truy vấn bảng `transcripts`, hệ thống sẽ bỏ qua bảng nội dung lượt thoại `chunks_turn` (RAG Engine) và trả về kết quả rỗng/sai lệch.
*   **Giải pháp tối ưu (Phân loại Query chặt chẽ & Fallback):**
    1.  **Thu hẹp SQL Heuristics:** Chỉ dịch SQL trực tiếp khi câu hỏi thuộc dạng tra cứu siêu dữ liệu thuần túy (như thời lượng cuộc gọi, ngày gọi cụ thể).
    2.  **Phân luồng RAG cho các câu hỏi hành động:** Bất kỳ câu hỏi nào chứa từ ngữ chỉ hành động, mối quan hệ (như "liên lạc với ai", "nói chuyện với ai") bắt buộc phải đi qua RAG Engine để quét văn bản.
    3.  **Tự động Fallback:** Nếu SQL Engine không trả về thông tin hoặc không khớp, hệ thống phải tự động chuyển hướng truy vấn sang RAG Engine thay vì kết luận ngay lập tức.

### Vấn đề 5: Ô nhiễm đại từ chung trong Entity Index ("担当者", "その人")
*   **Hiện trạng kỹ thuật (`src/entity_extractor.py` - dòng 92, 158):** Khi trích xuất thực thể, hệ thống tự động gán các đại từ chung như "担当者" (người phụ trách), "その人" (người đó) vào mảng `display_names` của mọi thực thể người.
*   **Rủi ro trên Production:** Khi người dùng hỏi một câu chứa từ "担当者", bộ lọc Tier 1 sẽ khớp trúng toàn bộ danh sách người tham gia hội thoại (`len(matched_entities) > 1`), lập tức kích hoạt luật chuyển hướng lên Tier 2 để xử lý tranh chấp. Điều này vô hiệu hóa bộ lọc nhanh của Tier 1, làm tăng độ trễ hệ thống và gây lãng phí tài nguyên.
*   **Giải pháp tối ưu (Làm sạch Entity Index & Dynamic Binding):**
    1.  **Làm sạch chỉ mục:** Chỉ lưu trữ danh từ riêng xác định (Proper Nouns) hoặc bí danh thực tế của tên đó (ví dụ: "中岡", "Nakaoka", "島田", "Valtes") trong DB `session_entity_index`.
    2.  **Liên kết đại từ động (Dynamic Binding):** Các đại từ chung ("担当者", "その人") sẽ được Router giải nghĩa động bằng cách ánh xạ vào thực thể đang hoạt động gần nhất (Last Active Entity) từ context cache của phiên làm việc hiện tại thay vì truy vấn tĩnh trong DB.

### Vấn đề 6: Viết cứng ngôn ngữ (Japanese-Centric Hardcoding) trong Direct Path
*   **Hiện trạng kỹ thuật (`src/orchestrator.py` - dòng 105-115):** Sử dụng các mảng từ khóa tiếng Nhật cứng (như `詳細`, `発言`, `会話`, `価格`) để kích hoạt Direct-Answer Path.
*   **Rủi ro trên Production:** Direct Path sẽ hoàn toàn bị tê liệt đối với các ngôn ngữ khác (tiếng Anh hoặc tiếng Việt), làm giảm hiệu năng hệ thống đối với khách hàng đa ngôn ngữ.
*   **Giải pháp tối ưu (Localized Pattern Dictionary):**
    *   Di chuyển tất cả các mảng từ khóa này vào tệp cấu hình `src/config.py` và phân loại theo mã ngôn ngữ (Language Code). Router sẽ tự động áp dụng bộ từ điển tương ứng dựa trên ngôn ngữ của truy vấn người dùng.

---

## 3. Bảng tổng hợp hành động (Action Item Matrix)

| Độ ưu tiên | Vấn đề | Tác động môi trường Production | Giải pháp đề xuất tối ưu |
| :--- | :--- | :--- | :--- |
| **Cao (Critical)** | **Ngưỡng Embedding cứng (`dist > 0.55`)** | Tê liệt chức năng nhận diện đổi chủ đề (`topic_shift`), kẹt cache ngữ cảnh cũ. | Sử dụng **Semantic Gap Analysis** (so sánh khoảng cách tương đối $d_1/d_2 < 0.65$) thay vì ngưỡng tuyệt đối. |
| **Cao (Critical)** | **Lọc trùng session số nhiều (`彼ら`)** | Phân giải sai đại từ khi hỏi về hai người trong cùng một cuộc gọi (trường hợp phổ biến nhất). | Đẩy toàn bộ việc phân giải đại từ số nhiều ("彼ら", "お二人") lên xử lý tập trung tại LLM Tier 2. |
| **Trung bình** | **Đại từ chung trong Entity Index** | Vô hiệu hóa bộ lọc nhanh Tier 1, ép hệ thống luôn chạy qua Tier 2 LLM khi hỏi về "担当者". | Xóa đại từ chung khỏi DB chỉ mục; thực hiện liên kết động (Dynamic Binding) theo thực thể hoạt động gần nhất. |
| **Trung bình** | **Nhận diện giới tính bằng hậu tố tên** | Lỗi phân giải đại từ giới tính "彼/彼女" khi giao tiếp bằng họ (Last Names) hoặc tên Katakana/Nước ngoài. | Trích xuất giới tính cấu trúc bằng LLM tại tầng Ingestion và lưu dưới dạng `JSONB` trong bảng `transcripts`. |
| **Thấp** | **SQL Heuristics cho từ khóa "相手"** | Bỏ qua dữ liệu trong bảng `chunks_turn` khi đối tượng được hỏi không nằm trực tiếp trong danh sách participants. | Giới hạn SQL Heuristics cho các câu hỏi siêu dữ liệu thuần túy; cấm áp dụng cho các câu hỏi hành động/quan hệ. |
| **Thấp** | **Từ khóa Direct Path tiếng Nhật cứng** | Tê liệt chức năng tối ưu hóa Direct Path đối với các truy vấn tiếng Anh/tiếng Việt. | Di chuyển từ khóa vào cấu hình `src/config.py` phân loại theo mã ngôn ngữ để bản địa hóa linh hoạt. |

---

## 4. Kế hoạch kiểm thử & Đánh giá sau cải tiến
Sau khi áp dụng các giải pháp trên, để xác minh tính tổng quát hóa của hệ thống, cần thực hiện quy trình kiểm thử sau:
1.  **Kiểm thử tích hợp mô hình Embedding thật:** Chạy hệ thống với một mô hình Embedding thực tế (như `multilingual-e5-small`) thay cho `MockSentenceTransformer` và kiểm tra xem tính năng chuyển/giữ chủ đề hoạt động có đúng như kỳ vọng hay không.
2.  **Kiểm thử dữ liệu ngoài miền (Out-of-Domain):** Nạp dữ liệu transcript từ một lĩnh vực hoàn toàn khác (ví dụ: Tài chính, Y tế) và đặt các câu hỏi đa phiên, kiểm tra xem hệ thống có bị nhầm lẫn luồng SQL/RAG hoặc phân giải sai thực thể hay không.
3.  **Kiểm thử đa ngôn ngữ:** Thực hiện các câu hỏi bằng tiếng Anh hoặc tiếng Việt có sử dụng đại từ số nhiều/đơn lẻ để kiểm chứng tính hiệu quả của cơ chế Localized Pattern.
