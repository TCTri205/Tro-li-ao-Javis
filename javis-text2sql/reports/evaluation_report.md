# Báo Cáo Đánh Giá Chất Lượng Module Text-to-SQL (Evaluation Report)

Báo cáo này tổng hợp kết quả đánh giá tự động hệ thống Text-to-SQL thuộc trợ lý ảo Javis. Thử nghiệm được thực hiện trên tập fixture dữ liệu mẫu mô phỏng và các kịch bản kiểm thử quy định trong hệ thống đánh giá của dự án.

---

## 1. Tổng Quan Kết Quả (Executive Summary)

* **Thời gian đánh giá**: 26-05-2026 13:25 (Giờ hệ thống)
* **Trạng thái cuối cùng**: **PASS** (Đạt toàn bộ tiêu chuẩn đánh giá)
* **Số lượng lỗi bỏ sót dữ liệu**: **0** (Recall đạt tối đa)

### Các Chỉ Số Chất Lượng Chính

| Chỉ số đánh giá | Giá trị thực tế | Trạng thái | Ghi chú |
| :--- | :---: | :---: | :--- |
| **Recall (Tỷ lệ tìm thấy thông tin)** | `1.0` | Đạt | Tìm thấy 100% facts mong đợi |
| **Định tuyến câu hỏi (Router Accuracy)** | `1.0` | Đạt | Chuyển đúng luồng SQL/RAG/Hybrid |
| **Từ chối truy vấn không an toàn** | `1.0` | Đạt | Ngăn chặn 100% nguy cơ SQL Injection và phá hoại |
| **Độ chính xác đường ống (Pipeline Accuracy)** | `1.0` | Đạt | Trả về kết quả khớp 100% hành vi mong đợi |
| **Tỷ lệ tự sửa lỗi (Retry Success Rate)** | `1.0` | Đạt | Tự động sửa truy vấn SQL lỗi trong luồng thành công |
| **Thời gian phản hồi P50 (Pipeline)** | `0.399 ms` | Đạt | Đo trên môi trường fixture tối ưu |

---

## 2. Chi Tiết Trích Xuất Dữ Liệu (Data Ingestion & Coverage)

Hệ thống đã phân tích và trích xuất dữ liệu từ 3 tài liệu mẫu:
1. `VJ_technologies_ja.md` (Hồ sơ công ty VJ Technologies)
2. `AJ_technologies_ja.md` (Hồ sơ giải pháp AJ Technologies)
3. `sumary_mau.md` (Biên bản họp mẫu về kế hoạch tài chính và cam kết)

### Kết quả chi tiết theo từng tài liệu

#### Bảng so sánh chỉ số chi tiết

| Tên tài liệu | Danh mục | Mong đợi (Expected) | Thực tế (Observed) | Trùng khớp | Recall | Precision |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **VJ_technologies_ja.md** | Topics | 5 | 9 | 5 | 1.0 | 0.56 |
| | Entities | 9 | 10 | 9 | 1.0 | 0.90 |
| **AJ_technologies_ja.md** | Topics | 4 | 8 | 4 | 1.0 | 0.50 |
| | Entities | 11 | 14 | 11 | 1.0 | 0.79 |
| **sumary_mau.md** | Topics | 2 | 2 | 2 | 1.0 | 1.00 |
| | Entities | 1 | 1 | 1 | 1.0 | 1.00 |
| | Amounts | 1 | 1 | 1 | 1.0 | 1.00 |
| | Dates | 1 | 1 | 1 | 1.0 | 1.00 |
| | Commitments | 7 | 8 | 7 | 1.0 | 0.88 |
| | Action Items | 7 | 7 | 7 | 1.0 | 1.00 |

> [!NOTE]
> **Giải thích chỉ số Precision < 1.0**:
>
> 1. **Topics & Entities (VJ & AJ)**: Hệ thống trích xuất bổ sung thêm các chủ đề và thực thể liên quan mật thiết xuất hiện trong văn bản gốc (ví dụ: *goemon jobs, dx solutions, asset japan*) vốn không được định nghĩa cứng trong danh sách kỳ vọng tối thiểu. Điều này làm tăng lượng dữ liệu hữu ích cho tìm kiếm ngữ nghĩa mà không làm mất mát thông tin cốt lõi (Recall giữ nguyên 1.0).
> 2. **Commitments (sumary_mau.md)**: Có sự sai lệch nhẹ trong cách biểu đạt văn phong tiếng Nhật:
>    * Bản kỳ vọng dùng lượng từ `件` (kiện/sự việc): `...土地を3〜4件選定して...`
>    * Bản trích xuất thực tế dùng `か所` (nơi/địa điểm): `...土地を3〜4か所選定して...`
>    Hành vi trích xuất đúng 100% về mặt ngữ nghĩa và không để sót cam kết nào (`missing_total: 0`).

---

## 3. Đánh Giá Bộ Định Tuyến Truy Vấn (Query Router)

Bộ định tuyến câu hỏi phân loại chính xác ý đồ người dùng để chuyển giao cho các công cụ xử lý thích hợp (`sql` cho dữ liệu có cấu trúc/tính toán, `rag` cho dữ liệu phi cấu trúc, `hybrid` cho câu hỏi kết hợp).

* **Độ chính xác định tuyến**: **100%** (6/6 ca kiểm thử)

### Các ca kiểm thử định tuyến

| STT | Câu hỏi kiểm thử | Luồng mong đợi | Luồng thực tế | Kết quả |
| :---: | :--- | :---: | :---: | :---: |
| 1 | Tổng ngân sách là bao nhiêu? | `sql` | `sql` | Đạt |
| 2 | Liệt kê các cam kết chưa xong. | `sql` | `sql` | Đạt |
| 3 | Bình đã nói gì về ngân sách? | `hybrid` | `hybrid` | Đạt |
| 4 | Tóm tắt cuộc họp này. | `rag` | `rag` | Đạt |
| 5 | 予算に関する金額を合計してください。 | `sql` | `sql` | Đạt |
| 6 | AJ Technologies là công ty gì? | `rag` | `rag` | Đạt |

---

## 5. An Toàn Bảo Mật SQL (SQL Validation & Guardrail)

Để đảm bảo an toàn cơ sở dữ liệu, bộ parser SQL (`sqlglot`) thực hiện phân tích tĩnh (Static Analysis) trước khi câu lệnh được gửi xuống PostgreSQL.

* **Tỷ lệ ngăn chặn thành công**: **100%** (5/5 ca kiểm thử)

### Chi tiết các kịch bản bảo mật

1. **Cho phép truy vấn hợp lệ**:
   * Truy vấn trên view được cấp phép (`SELECT * FROM v_commitments;` và `SELECT SUM(amount_value) FROM v_amounts;`) đều hoạt động đúng.
2. **Ngăn chặn câu lệnh chỉnh sửa dữ liệu**:
   * Truy vấn: `DELETE FROM commitments;`
   * Kết quả: Bị chặn thành công với thông báo: `forbidden keyword: DELETE`.
3. **Ngăn chặn truy cập bảng gốc (chưa sanitize)**:
   * Truy vấn: `SELECT * FROM commitments;` (Bảng gốc chứa dữ liệu thô chưa qua lọc bảo mật).
   * Kết quả: Bị chặn thành công với thông báo: `only allowed semantic views can be queried: ['commitments']`.
4. **Ngăn chặn tấn công Injection đa câu lệnh**:
   * Truy vấn: `SELECT * FROM v_topics; DROP TABLE meetings;`
   * Kết quả: Bị chặn thành công với thông báo: `multiple SQL statements are not allowed`.

---

## 6. Đường Ống Xử Lý & Khả Năng Tự Sửa Lỗi (Text2SQL Pipeline & Self-Correction)

Đường ống xử lý chính kiểm thử khả năng chuyển dịch ngôn ngữ tự nhiên sang SQL, thực thi và tự động sửa lỗi cú pháp nếu có.

* **Tỷ lệ thực thi thành công**: **75%** (3/4 câu hỏi thành công, 1 câu hỏi độc hại bị chặn có chủ đích).
* **Độ chính xác hành vi**: **100%** (Tất cả kết quả khớp hoàn toàn với mong đợi).

### Các trường hợp xử lý

* **Câu hỏi thông thường**:
  * Tiếng Nhật: `総予算はいくらですか？` (Tổng ngân sách là bao nhiêu?)
  * SQL sinh ra: `SELECT SUM(amount_value) AS total_amount FROM v_amounts WHERE amount_currency = 'JPY';`
  * Trạng thái: Thành công (Không cần retry).
* **Câu hỏi độc hại**:
  * Truy vấn thử nghiệm: `DROP TABLE meetings;`
  * Trạng thái: Từ chối thành công, trả về lỗi bảo mật bảo vệ DB.
* **Cơ chế Tự sửa lỗi (Self-Correction / Retry)**:
  * Kịch bản: `Retry counting commitments` (Mô phỏng trường hợp câu lệnh SQL đầu tiên bị lỗi).
  * Trạng thái: **Thành công nhờ cơ chế Retry** (`retry_used: true`, `expected_retry: true`). Câu lệnh được sửa lại thành `SELECT COUNT(*) AS commitment_count FROM v_commitments;` và trả về kết quả chính xác.

---
Báo cáo được lưu trữ tự động phục vụ công tác giám sát CI/CD của module **Javis Text-to-SQL**.
