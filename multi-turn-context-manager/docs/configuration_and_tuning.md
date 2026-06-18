# Cấu hình và Tinh chỉnh Hệ thống (Configuration & Tuning)

Tài liệu này chi tiết các tham số cấu hình, từ khóa hệ thống và các ngưỡng (threshold) được sử dụng để điều chỉnh hành vi của Lớp Điều phối Ngữ cảnh.

## 1. Cấu hình Từ khóa (Keywords Configuration)

Các từ khóa này được định nghĩa trong `src/config.py` và được Tier 1 Router sử dụng để phán đoán Pipeline mục tiêu nhanh chóng.

### 1.1. SQL Keywords
Dùng để nhận diện các câu hỏi về dữ liệu cấu trúc (thời gian, người tham gia, số lượng).
*   **Ví dụ:** `選択`, `カウント`, `平均`, `時間`, `通話`, `日付`, `何時`, `誰`, `件数`, `名前`, `会社`.

### 1.2. RAG Keywords
Dùng để nhận diện các câu hỏi về nội dung, chi tiết hội thoại hoặc kiến thức chuyên môn bất động sản.
*   **Ví dụ:** `要約`, `内容`, `詳細`, `発言`, `翻訳`, `ドキュメント`, `内見`, `契約`, `物件`, `登記`, `賃貸`, `売買`.

### 1.3. WEB Keywords
Dùng để nhận diện các yêu cầu tìm kiếm thông tin bên ngoài.
*   **Ví dụ:** `天気`, `株価`, `ニュース`, `ネット`, `検索`, `グーグル`.

## 2. Các ngưỡng Định tuyến và Nhúng (Routing & Embedding Thresholds)

Hệ thống sử dụng pgvector với khoảng cách Cosine (`<=>`) để so sánh truy vấn mới với các slot cache hiện có.

| Tham số | Giá trị | Ý nghĩa |
| :--- | :--- | :--- |
| **Hit Threshold (Vùng Xanh)** | `< 0.22` | Khoảng cách nhỏ (Similarity > 0.78). Coi là cùng một chủ đề (Cache Hit). |
| **Shift Threshold (Vùng Đỏ)** | `> 0.55` | Khoảng cách lớn (Similarity < 0.45). Coi là chủ đề mới (Topic Shift). |
| **Gray Area (Vùng Xám)** | `0.22 - 0.55` | Chuyển sang Tier 2 (LLM) để quyết định. |
| **Embedding Timeout** | `1.0s` | Thời gian chờ tối đa để tạo vector. Nếu quá hạn, tự động fallback sang Tier 2. |

## 3. Cấu hình Bộ nhớ đệm (Cache Settings)

| Tham số | Giá trị | Ý nghĩa |
| :--- | :--- | :--- |
| **MAX_CACHE_SLOTS** | `3` | Số lượng slot cache tối đa cho mỗi phiên (Session). Áp dụng chính sách LRU để xóa slot cũ nhất. |
| **CACHE_TTL_WEB** | `3600s` | Thời gian sống của cache pipeline WEB (1 giờ). |
| **CACHE_TTL_SQL** | `86400s` | Thời gian sống của cache pipeline SQL (24 giờ). |

## 4. Tham số Thời gian chờ và Thử lại (Timeouts & Retries)

| Tham số | Giá trị | Ý nghĩa |
| :--- | :--- | :--- |
| **Lock Timeout** | `8.0s` | Thời gian chờ tối đa để lấy Advisory Lock. Nếu quá hạn, trả về lỗi Timeout. |
| **Engine Timeout** | `30.0s` | Thời gian chờ tối đa cho một Engine (SQL/RAG/WEB). |
| **Circuit Breaker Cooldown** | `30s` | Thời gian tạm dừng của một engine sau khi bị ngắt mạch (Open state). |
| **Self-Check Retries** | `2` | Số lần tối đa LLM được phép tạo lại câu trả lời nếu không vượt qua bước xác minh. |

## 5. Định dạng Phản hồi SQL (SQL Friendly Keys)

Để câu trả lời trực tiếp (Direct Path) thân thiện hơn, các cột SQL được ánh xạ sang nhãn tiếng Nhật:
*   `duration` -> `通話時間`
*   `meeting_date` / `date` -> `日付`
*   `summary` -> `要約`
*   `speaker` -> `話者`
*   `participants` -> `参加者`
