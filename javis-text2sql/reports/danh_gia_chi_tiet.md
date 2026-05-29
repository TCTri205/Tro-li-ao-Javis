# BÁO CÁO ĐÁNH GIÁ CHI TIẾT TEXT2SQL (99 TESTCASES)
*Thời gian thực hiện: 2026-05-29 11:14:52*
*Môi trường kết nối cơ sở dữ liệu: Live PostgreSQL*

## 1. TỔNG QUAN KẾT QUẢ ĐÁNH GIÁ
| Tiêu chí | Tổng số | Đúng | Sai | Tỷ lệ đạt |
| :--- | :---: | :---: | :---: | :---: |
| **Đánh giá tổng hợp** | 99 | 89 | 10 | 89.9% |

## 2. DANH SÁCH CHI TIẾT CÁC TESTCASE
| ID | Câu hỏi (Tiếng Nhật) | Câu dịch (Tiếng Việt) | Đánh giá | Trạng thái | Chi tiết đánh giá |
| :---: | :--- | :--- | :---: | :---: | :--- |
| 1 | JPYで言及された総予算はいくらですか？ | Tổng ngân sách bằng JPY | Đúng | ✅ Đúng | Đúng (GROUP BY amount_currency dư thừa) |
| 2 | budgetというコンテキストを持つ金額をすべて合計してください。 | Tổng số tiền của các khoản có ngữ cảnh là 'budget' | Đúng | ✅ Đúng | Đúng |
| 3 | すべての金額を通貨とコンテキスト付きで一覧表示してください。 | Liệt kê tất cả số tiền kèm theo loại tiền tệ và ngữ cảnh | Đúng | ✅ Đúng | Đúng |
| 4 | 未完了のコミットメントはいくつありますか？ | Có bao nhiêu cam kết chưa hoàn thành (pending)? | Đúng | ✅ Đúng | Đúng |
| 5 | 完了済みのコミットメントはいくつありますか？ | Có bao nhiêu cam kết đã hoàn thành (done)? | Sai | ❌ Sai | Sai (do sql dùng status = 'completed' nhưng trong DB lại định nghĩa status IN ('pending', 'done', 'cancelled')) -> ko có completed |
| 6 | すべてのコミットメントを担当者、アクション、期限付きで一覧表示してください。 | Liệt kê tất cả các cam kết kèm người phụ trách, hành động và hạn chót | Đúng | ✅ Đúng | Đúng |
| 7 | 2026-06-01より前が期限のコミットメントを一覧表示してください。 | Liệt kê các cam kết có hạn chót trước ngày 2026-06-01 | Đúng | ✅ Đúng | Đúng |
| 8 | 2026-05-30より後が期限のコミットメントを一覧表示してください。 | Liệt kê các cam kết có hạn chót sau ngày 2026-05-30 | Đúng | ✅ Đúng | Đúng |
| 9 | 重要度スコアが4以上のアクションアイテムを表示してください。 | Hiển thị các hành động có điểm quan trọng từ 4 trở lên | Đúng | ✅ Đúng | Đúng |
| 10 | すべての未解決の質問を重要度スコア付きで表示してください。 | Hiển thị tất cả câu hỏi chưa giải quyết kèm điểm quan trọng | Đúng | ✅ Đúng | Đúng |
| 11 | 重要度スコアが4以上のネガティブな発言を一覧表示してください。 | Hiển thị các phát biểu tiêu cực có điểm quan trọng từ 4 trở lên | Đúng | ✅ Đúng | Đúng |
| 12 | 感情別に発言数をカウントしてください。 | Đếm số phát biểu theo từng cảm xúc | Đúng | ✅ Đúng | Đúng |
| 13 | タイトルにVJを含む会議のトピックを一覧表示してください。 | Liệt kê các chủ đề (topics) của cuộc họp có tiêu đề chứa 'VJ' | Đúng | ✅ Đúng | Đúng |
| 14 | タイトルにAJを含む会議のトピックを一覧表示してください。 | Liệt kê các chủ đề (topics) của cuộc họp có tiêu đề chứa 'AJ' | Sai | ❌ Sai | Sai (trả dư entity, thừa rows / thiếu filter: source_type = 'topic') |
| 15 | タイトルにVJを含む会議の固有エンティティを一覧表示してください。 | Liệt kê các thực thể định danh (named entities) của cuộc họp có tiêu đề chứa 'VJ' | Sai | ❌ Sai | Sai (KHÔNG trả entities / semantic sai hoàn toàn, query sai bảng) |
| 16 | タイトルにAJを含む会議の固有エンティティを一覧表示してください。 | Liệt kê các thực thể định danh (named entities) của cuộc họp có tiêu đề chứa 'AJ' | Sai | ❌ Sai | Sai (KHÔNG trả entities / semantic sai hoàn toàn, query sai bảng) |
| 17 | budgetに言及している発話を一覧表示してください。 | budgetに言及している発話を一覧表示してください。 | Đúng | ✅ Đúng | Đúng |
| 18 | 話者ごとの発話数をカウントしてください。 | Đếm số phát biểu của mỗi người nói | Đúng | ✅ Đúng | Đúng |
| 19 | VJ Technologiesに言及している発話を一覧表示してください。 | Liệt kê các phát biểu đề cập đến 'VJ Technologies' | Đúng | ✅ Đúng | Đúng |
| 20 | AJ Technologiesに言及している発話を一覧表示してください。 | Liệt kê các phát biểu đề cập đến 'AJ Technologies' | Đúng | ✅ Đúng | Đúng |
| 21 | 通貨ごとにamount_valueを合計してください。 | Tổng số tiền theo từng loại tiền tệ | Đúng | ✅ Đúng | Đúng |
| 22 | 会議タイトルごとにamount_valueを合計してください。 | Tổng số tiền theo từng cuộc họp | Đúng | ✅ Đúng | Đúng |
| 23 | 通貨がJPYの金額を一覧表示してください。 | Liệt kê các số tiền có đơn vị là JPY | Đúng | ✅ Đúng | Đúng |
| 24 | コンテキストにbudgetを含む金額を一覧表示してください。 | Liệt kê các số tiền có ngữ cảnh chứa 'budget' | Đúng | ✅ Đúng | Đúng |
| 25 | アクションアイテム数をカウントしてください。 | Đếm tổng số hành động cần làm (action items) | Đúng | ✅ Đúng | Đúng |
| 26 | アクションアイテムを会議日付の降順で一覧表示してください。 | Liệt kê các hành động kèm ngày họp | Đúng | ✅ Đúng | Đúng |
| 27 | ステータスごとにコミットメント数を集計してください。 | Đếm số cam kết theo từng trạng thái | Đúng | ✅ Đúng | Đúng |
| 28 | 担当者名にYamashitaを含むコミットメントを一覧表示してください。 | Liệt kê các cam kết của người phụ trách 'Yamashita' | Đúng | ✅ Đúng | Đúng |
| 29 | 担当者名にYoshioを含むコミットメントを一覧表示してください。 | Liệt kê các cam kết của người phụ trách 'Yoshio' | Đúng | ✅ Đúng | Đúng |
| 30 | 言及されたすべての日付を一覧表示してください。 | Liệt kê tất cả các ngày được đề cập | Đúng | ✅ Đúng | Đúng |
| 31 | 言及された日付を会議タイトル付きで一覧表示してください。 | Liệt kê các ngày được đề cập kèm tiêu đề cuộc họp | Đúng | ✅ Đúng | Đúng |
| 32 | 会議タイトルごとに言及された日付数をカウントしてください。 | Đếm số ngày được đề cập theo từng cuộc họp | Đúng | ✅ Đúng | Đúng |
| 33 | トピックにEnergyを含むトピックを一覧表示してください。 | Liệt kê các chủ đề (topics) có chứa 'Energy' | Sai | ❌ Sai | Sai (trả dư entity, thừa rows / thiếu filter: source_type = 'topic') |
| 34 | トピックにGoEMONを含むトピックを一覧表示してください。 | Liệt kê các chủ đề (topics) có chứa 'GoEMON' | Đúng | ✅ Đúng | Đúng |
| 35 | トピックにDXを含むトピックを一覧表示してください。 | Liệt kê các chủ đề (topics) có chứa 'DX' | Đúng | ✅ Đúng | Đúng |
| 36 | トピックにAIを含むトピックを一覧表示してください。 | Liệt kê các chủ đề (topics) có chứa 'AI' | Đúng | ✅ Đúng | Đúng |
| 37 | アクションにbudgetを含むコミットメントを一覧表示してください。 | Liệt kê các cam kết có hành động chứa 'budget' | Đúng | ✅ Đúng | Đúng |
| 38 | アクションテキストにbudgetを含むアクションアイテムを一覧表示してください。 | Liệt kê các hành động có chứa 'budget' | Đúng | ✅ Đúng | Đúng |
| 39 | 重要度スコアが5以上の発言を一覧表示してください。 | Liệt kê các phát biểu có điểm quan trọng từ 5 trở lên | Đúng | ✅ Đúng | Đúng |
| 40 | ネガティブ感情の発話を一覧表示してください。 | Liệt kê các phát biểu mang cảm xúc tiêu cực (negative) | Đúng | ✅ Đúng | Đúng |
| 41 | topics内の異なるmeeting_id数をカウントしてください。 | Đếm số cuộc họp khác nhau trong bảng topics | Đúng | ✅ Đúng | Đúng |
| 42 | commitments内の異なるmeeting_id数をカウントしてください。 | Đếm số cuộc họp khác nhau trong bảng commitments | Đúng | ✅ Đúng | Đúng |
| 43 | topicsから会議タイトルと日付を一覧表示してください。 | Liệt kê tiêu đề và ngày họp từ bảng topics | Đúng | ✅ Đúng | Đúng |
| 44 | commitmentsから会議タイトルと日付を一覧表示してください。 | Liệt kê tiêu đề và ngày họp từ bảng commitments | Đúng | ✅ Đúng | Đúng |
| 45 | amountsから会議タイトルと日付を一覧表示してください。 | Liệt kê tiêu đề và ngày họp từ bảng amounts | Đúng | ✅ Đúng | Đúng |
| 46 | タイトルにHousingを含む会議の発話を一覧表示してください。 | タイトルにHousingを含む会議の発話を一覧表示してください。 | Đúng | ✅ Đúng | Đúng |
| 47 | タイトルにHousingを含む会議のすべてのコミットメントを表示してください。 | Hiển thị tất cả cam kết của các cuộc họp có tiêu đề chứa 'Housing' | Đúng | ✅ Đúng | Đúng |
| 48 | タイトルにHousingを含む会議のコミットメント数をカウントしてください。 | Đếm số cam kết của các cuộc họp có tiêu đề chứa 'Housing' | Đúng | ✅ Đúng | Đúng |
| 49 | タイトルにHousingを含む会議の金額を表示してください。 | Hiển thị số tiền của các cuộc họp có tiêu đề chứa 'Housing' | Đúng | ✅ Đúng | Đúng |
| 50 | source_typeがentityのトピックを一覧表示してください。 | Liệt kê các thực thể (source_type = 'entity') | Đúng | ✅ Đúng | Đúng |
| 51 | source_typeごとにトピック数をカウントしてください。 | Đếm số chủ đề theo từng loại source_type | Đúng | ✅ Đúng | Đúng |
| 52 | 会議日付が2026-05-26のトピックを一覧表示してください。 | Liệt kê các chủ đề của cuộc họp ngày 2026-05-26 | Đúng | ✅ Đúng | Đúng |
| 53 | 会議日付が2026-05-26のコミットメントを一覧表示してください。 | Liệt kê các cam kết của cuộc họp ngày 2026-05-26 | Đúng | ✅ Đúng | Đúng |
| 54 | 会議日付が2026-05-26のアクションアイテムを一覧表示してください。 | Liệt kê các hành động kèm ngày họp | Đúng | ✅ Đúng | Đúng |
| 55 | 会議日付が2026-05-26の未解決質問を一覧表示してください。 | Liệt kê các câu hỏi chưa giải quyết của cuộc họp ngày 2026-05-26 | Đúng | ✅ Đúng | Đúng |
| 56 | amount_valueが1000以上の金額を一覧表示してください。 | Liệt kê các số tiền có giá trị từ 1000 trở lên | Đúng | ✅ Đúng | Đúng |
| 57 | 金額をamount_valueの降順で一覧表示してください。 | Liệt kê các khoản tiền sắp xếp giảm dần theo giá trị | Đúng | ✅ Đúng | Đúng |
| 58 | コンテキストにelectricを含む総金額を表示してください。 | Tổng số tiền của các khoản có ngữ cảnh chứa 'electric' | Đúng | ✅ Đúng | Đúng |
| 59 | コンテキストにbudgetを含む総金額を表示してください。 | Tổng số tiền của các khoản có ngữ cảnh chứa 'budget' | Đúng | ✅ Đúng | Đúng |
| 60 | 話者がdocumentの発話数をカウントしてください。 | Đếm số phát biểu của người nói 'document' | Đúng | ✅ Đúng | Đúng |
| 61 | 異なる話者を一覧表示してください。 | Liệt kê các người nói khác nhau | Đúng | ✅ Đúng | Đúng |
| 62 | 異なる話者数をカウントしてください。 | Đếm số người nói khác nhau | Đúng | ✅ Đúng | Đúng |
| 63 | Energy Japanに言及している発話を一覧表示してください。 | Liệt kê các phát biểu đề cập đến 'Energy Japan' | Đúng | ✅ Đúng | Đúng |
| 64 | GoEMONに言及している発話を一覧表示してください。 | Liệt kê các phát biểu đề cập đến 'GoEMON' | Đúng | ✅ Đúng | Đúng |
| 65 | AIに言及している発話を一覧表示してください。 | Liệt kê các phát biểu đề cập đến 'AI' | Đúng | ✅ Đúng | Đúng |
| 66 | トピックを会議タイトル付きで一覧表示してください。 | Liệt kê chủ đề kèm theo tiêu đề cuộc họp | Sai | ❌ Sai | Sai (trả dư entity, thừa rows / thiếu filter: source_type = 'topic') |
| 67 | コミットメントを会議タイトルと担当者付きで一覧表示してください。 | Liệt kê cam kết kèm tiêu đề cuộc họp và người phụ trách | Đúng | ✅ Đúng | Đúng |
| 68 | アクションアイテムを会議タイトルとアクションテキスト付きで一覧表示してください。 | Liệt kê các hành động kèm tiêu đề cuộc họp và văn bản hành động | Đúng | ✅ Đúng | Đúng |
| 69 | 未解決質問を会議タイトルと質問テキスト付きで一覧表示してください。 | Liệt kê câu hỏi chưa giải quyết kèm tiêu đề cuộc họp | Đúng | ✅ Đúng | Đúng |
| 70 | 会議タイトルごとに未完了コミットメント数をカウントしてください。 | Đếm số cam kết chưa hoàn thành (pending) theo từng cuộc họp | Đúng | ✅ Đúng | Đúng |
| 71 | 会議タイトルごとに完了済みコミットメント数をカウントしてください。 | Đếm số cam kết đã hoàn thành (done) theo từng cuộc họp | Sai | ❌ Sai | Sai (do sql dùng status = 'completed' nhưng trong DB lại định nghĩa status IN ('pending', 'done', 'cancelled')) -> ko có completed |
| 72 | deadline_dateがないコミットメントを一覧表示してください。 | Liệt kê các cam kết không có ngày hạn chót | Đúng | ✅ Đúng | Đúng |
| 73 | deadline_dateがあるコミットメントを一覧表示してください。 | Liệt kê các cam kết có ngày hạn chót | Đúng | ✅ Đúng | Đúng |
| 74 | confidenceが0.8以上の日付を一覧表示してください。 | Liệt kê các ngày có mức độ tin cậy từ 0.8 trở lên | Đúng | ✅ Đúng | Đúng |
| 75 | confidenceが1.0未満の日付を一覧表示してください。 | Liệt kê các ngày có mức độ tin cậy nhỏ hơn 1.0 | Đúng | ✅ Đúng | Đúng |
| 76 | 重要度スコアが4以上のアクションアイテム数をカウントしてください。 | Hiển thị các hành động có điểm quan trọng từ 4 trở lên | Đúng | ✅ Đúng | Đúng |
| 77 | 重要度スコアが4以上の未解決質問数をカウントしてください。 | Đếm số câu hỏi chưa giải quyết có điểm quan trọng từ 4 trở lên | Đúng | ✅ Đúng | Đúng |
| 78 | 感情がneutralの発言を一覧表示してください。 | Liệt kê các phát biểu có cảm xúc trung lập (neutral) | Đúng | ✅ Đúng | Đúng |
| 79 | 会議タイトルごとに発言数をカウントしてください。 | Đếm số phát biểu theo từng cuộc họp | Đúng | ✅ Đúng | Đúng |
| 80 | 会議タイトルごとに発話数をカウントしてください。 | Đếm số phát biểu theo từng cuộc họp | Đúng | ✅ Đúng | Đúng |
| 81 | 発話数が多い上位5人の話者を一覧表示してください。 | Liệt kê 5 người nói phát biểu nhiều nhất | Đúng | ✅ Đúng | Đúng |
| 82 | 4500に言及している発話を一覧表示してください。 | Liệt kê các phát biểu đề cập đến số tiền 4,500 | Đúng | ✅ Đúng | Đúng |
| 83 | unitにmanを含むamount_valueを合計してください。 | Tổng số tiền của các khoản có đơn vị chứa 'man' | Đúng | ✅ Đúng | Đúng |
| 84 | タイトルにVJを含む会議の金額コンテキストと値を一覧表示してください。 | Liệt kê số tiền và ngữ cảnh của cuộc họp chứa 'VJ' | Đúng | ✅ Đúng | Đúng |
| 85 | VJ Technologiesに言及している会議タイトルを一覧表示してください。 | Liệt kê tiêu đề cuộc họp đề cập đến 'VJ Technologies' | Đúng | ✅ Đúng | Đúng |
| 86 | AJ Technologiesに言及している会議タイトルを一覧表示してください。 | Liệt kê tiêu đề cuộc họp đề cập đến 'AJ Technologies' | Đúng | ✅ Đúng | Đúng |
| 87 | ONE Financial Serviceに言及している会議タイトルを一覧表示してください。 | Liệt kê tiêu đề cuộc họp đề cập đến 'ONE Financial Service' | Đúng | ✅ Đúng | Đúng |
| 88 | Energy Japanに言及している会議タイトルを一覧表示してください。 | Liệt kê tiêu đề cuộc họp đề cập đến 'Energy Japan' | Đúng | ✅ Đúng | Đúng |
| 89 | コミットメントをdeadline_dateの昇順で一覧表示してください。 | Sắp xếp cam kết theo thứ tự tăng dần của ngày hạn chót | Đúng | ✅ Đúng | Đúng |
| 90 | deadlineにthis weekを含むコミットメントを一覧表示してください。 | Liệt kê các cam kết có hạn chót trong tuần này | Đúng | ✅ Đúng | Đúng |
| 91 | アクションアイテムを重要度スコアの降順で一覧表示してください。 | Sắp xếp các hành động giảm dần theo điểm quan trọng | Đúng | ✅ Đúng | Đúng |
| 92 | 未解決質問を重要度スコアの降順で一覧表示してください。 | Sắp xếp các câu hỏi chưa giải quyết giảm dần theo điểm quan trọng | Đúng | ✅ Đúng | Đúng |
| 93 | 発言を重要度スコアの降順で一覧表示してください。 | Sắp xếp các phát biểu giảm dần theo điểm quan trọng | Đúng | ✅ Đúng | Đúng |
| 94 | 会議タイトルごとにトピック数をカウントしてください。 | Đếm số chủ đề theo từng cuộc họp | Sai | ❌ Sai | Sai (trả dư entity, thừa rows / thiếu filter: source_type = 'topic') |
| 95 | タイトルにcompany profileを含む会議のトピックを一覧表示してください。 | Liệt kê các chủ đề (topics) của cuộc họp có tiêu đề chứa 'company profile' | Sai | ❌ Sai | Sai (trả dư entity, thừa rows / thiếu filter: source_type = 'topic') |
| 96 | タイトルにcompany profileを含む会議のエンティティを一覧表示してください。 | Liệt kê các thực thể (entities) của cuộc họp có tiêu đề chứa 'company profile' | Sai | ❌ Sai | Sai (Lỗi thực thi: column s.entity does not exist) |
| 97 | タイトルにsummaryを含む会議のトピックを一覧表示してください。 | Liệt kê các chủ đề (topics) của cuộc họp có tiêu đề chứa 'summary' | Đúng | ✅ Đúng | Đúng |
| 98 | タイトルにsummaryを含む会議のコミットメント数をカウントしてください。 | Đếm số cam kết của các cuộc họp có tiêu đề chứa 'summary' | Đúng | ✅ Đúng | Đúng |
| 99 | タイトルにsummaryを含む会議の金額数をカウントしてください。 | Đếm số khoản tiền của các cuộc họp có tiêu đề chứa 'summary' | Đúng | ✅ Đúng | Đúng |