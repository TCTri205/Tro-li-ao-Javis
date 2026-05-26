Nghiên cứu Hệ thống về các Phương pháp Chuyển đổi Ngôn ngữ Tự nhiên sang Truy vấn SQL: Từ Tiếp cận Truyền thống, Mô hình Ngôn ngữ Lớn, Tạo sinh Tăng cường Tra cứu đến Hệ sinh thái Công cụ Hiện đại
Tiến trình Phát triển và các Cột mốc Công nghệ
Lịch sử của giao diện ngôn ngữ tự nhiên cho cơ sở dữ liệu (NLIDB) bắt đầu từ những năm 1970 với mong muốn giúp người dùng không có kỹ năng lập trình dễ dàng truy xuất thông tin từ cơ sở dữ liệu quan hệ.1 Thời kỳ đầu tiên này được thống trị bởi các phương pháp dựa trên luật cứng, khớp mẫu ngữ pháp và cú pháp cụ thể.2 Hệ thống LUNAR phát triển vào năm 1973 là một minh chứng lịch sử, hỗ trợ các nhà khoa học đặt câu hỏi bằng tiếng Anh để truy xuất dữ liệu về các mẫu đá mặt trăng.1 Các hệ thống này thường phân loại thành bốn nhóm tiếp cận chính bao gồm dựa trên từ khóa, dựa trên mẫu định sẵn, dựa trên phân tích cú pháp và dựa trên ngữ pháp ngữ nghĩa.2 Việc tiền xử lý ngôn ngữ tự nhiên trong thời kỳ này đòi hỏi các kỹ thuật thủ công phức tạp như tách từ (stemming), gán nhãn từ loại (POS tagging), nhận diện thực thể có tên (NER), phân tích cú pháp phụ thuộc và sử dụng biểu thức chính quy.2 Hệ thống LADDER sử dụng ngữ pháp ngữ nghĩa để đan xen quá trình xử lý cú pháp và ngữ nghĩa, trong khi ngôn ngữ FLIP cung cấp cơ chế khớp mẫu dựa trên cấu trúc LISP.4 Dù đem lại độ chính xác cao trong một phạm vi hoạt động cực kỳ hẹp, các hệ thống dựa trên luật này lộ rõ điểm yếu là chi phí phát triển quá lớn, tính cứng nhắc cao và hoàn toàn không có khả năng chuyển đổi sang các cơ sở dữ liệu mới.5
Sự dịch chuyển công nghệ lớn thứ hai diễn ra vào giữa thập niên 2010 với sự bùng nổ của mạng học sâu và kiến trúc chuỗi-sang-chuỗi (Sequence-to-Sequence).1 Kể từ nghiên cứu tiên phong của Dong và Lapata năm 2016, cơ chế chú ý (attention mechanism) đã được ứng dụng để dịch trực tiếp câu hỏi người dùng thành cú pháp SQL.7 Các mô hình thời kỳ này như Seq2SQL và SQLNet đã tự động hóa việc học ánh xạ mà không cần thiết lập luật thủ công.1 Tuy nhiên, do thiếu khả năng hiểu biết sâu sắc về lược đồ dữ liệu và mối quan hệ thực thể, các mạng LSTM này thường thất bại khi gặp các phép kết nối (JOIN) nhiều bảng hoặc các điều kiện lọc lồng nhau phức tạp.5 Để khắc phục, các mô hình ngôn ngữ tiền huấn luyện chuyên biệt (PLM) đã ra đời.7 RAT-SQL đã giải quyết bài toán liên kết lược đồ bằng cách sử dụng mạng đồ thị không đồng nhất để biểu diễn cấu trúc dữ liệu, trong khi RESDSQL chia tách quá trình thành hai giai đoạn phân biệt là phân loại lược đồ và dịch cú pháp.7 Dẫu vậy, các mô hình PLM vẫn bị giới hạn bởi số lượng tham số, khiến chúng gặp rào cản lớn khi đối mặt với các truy vấn đòi hỏi suy luận logic đa bước hoặc khả năng tổng quát hóa đa miền.7
Sự xuất hiện của các mô hình ngôn ngữ lớn (LLM) đã tái định hình toàn bộ lĩnh vực Text-to-SQL thông qua hai chiến lược cốt lõi là học trong ngữ cảnh (In-Context Learning - ICL) và tinh chỉnh chuyên biệt (Supervised Fine-Tuning - SFT).7 Khả năng hiểu ngữ nghĩa vượt trội của các LLM như GPT-4 hay Claude cho phép hệ thống hiểu sâu sắc câu hỏi của người dùng, liên kết chính xác các thực thể với lược đồ dữ liệu và sinh mã SQL tối ưu cho từng dialect cụ thể.10 Trong kỷ nguyên này, Text-to-SQL không còn là một bài toán dịch một bước (monolithic pipeline) mà đã phát triển thành một hệ thống tác nhân phức hợp, tích hợp khả năng tự lập kế hoạch, suy luận từng bước và tự động sửa lỗi dựa trên phản hồi thực tế từ hệ quản trị cơ sở dữ liệu.12
Thách thức Kỹ thuật và Mô hình Phân rã Đa Tác nhân
Việc áp dụng một lời gọi LLM đơn lẻ và trực tiếp cho các tác vụ Text-to-SQL doanh nghiệp thường gặp phải ba rào cản vật lý nghiêm trọng.13 Rào cản thứ nhất là sự bão hòa cửa sổ ngữ cảnh khi cố gắng đưa toàn bộ mã định nghĩa dữ liệu (DDL) của cơ sở dữ liệu lớn vào prompt, dẫn đến hiện tượng mô hình mất tập trung ở giữa và bỏ sót thông tin quan trọng.13 Rào cản thứ hai là sự lệch suy luận xảy ra do mô hình bị quá tải nhận thức khi phải thực hiện đồng thời việc hiểu ý định, lập kế hoạch logic, liên kết lược đồ và viết mã cú pháp.13 Rào cản thứ ba là hệ thống vòng hở hoàn toàn không có khả năng tự kiểm tra và sửa lỗi khi câu lệnh SQL sinh ra chứa sai sót.13 Do đó, xu hướng thiết kế hiện đại đã chuyển dịch sang các khung kiến trúc đa tác nhân chuyên biệt hóa nhằm chia nhỏ các nhiệm vụ nhận thức phức tạp này.12
Nhiều khung kiến trúc tác nhân tiên tiến đã chứng minh hiệu quả vượt trội so với các tiếp cận nguyên khối truyền thống. Hệ thống DIN-SQL phân rã toàn bộ nhiệm vụ thành bốn mô-đun độc lập bao gồm liên kết lược đồ, phân rã câu hỏi, tạo truy vấn và tự sửa lỗi dựa trên các hướng dẫn sửa lỗi được thiết kế bởi chuyên gia.14 Khung tác nhân MAC-SQL tiến xa hơn khi phối hợp ba tác nhân chuyên biệt là tác nhân chọn lọc (Selector) giúp thu gọn cơ sở dữ liệu lớn thành phân vùng nhỏ hơn để giảm nhiễu, tác nhân phân rã (Decomposer) chia nhỏ câu hỏi phức tạp thành các câu hỏi phụ, và tác nhân tinh chỉnh (Refiner) để sửa lỗi hệ thống.16 MAC-SQL cũng giới thiệu mô hình tinh chỉnh chỉ dẫn SQL-Llama (7B) giúp tối ưu hóa chi phí vận hành.16 Trong khi đó, hệ thống PExA đạt độ chính xác thực thi lên tới 70.2% trên bộ dữ liệu Spider 2.0 nhờ việc tách biệt hoàn toàn khâu lập kế hoạch logic bằng ngôn ngữ tự nhiên trước khi cho phép tác nhân sinh mã SQL.13 Mô hình STaR-SQL áp dụng phương pháp tự học suy luận bằng cách huấn luyện mô hình sinh các lý giải chi tiết đi kèm truy vấn đúng, đồng thời sử dụng một mô hình phần thưởng giám sát kết quả (ORM) đóng vai trò bộ kiểm chứng để nâng cao độ chính xác lên 86.6% trên Spider.7 Cuối cùng, hệ thống X-SQL chứng minh rằng việc kết hợp mô-đun liên kết lược đồ tinh chỉnh SFT (X-Linking), mô-đun giải nghĩa dữ liệu bằng ngôn ngữ tự nhiên (X-Admin) và cơ chế đa mô hình LLM chuyên biệt có thể cải thiện hiệu năng thêm 10.9% để đạt trạng thái xuất sắc nhất.14

Khung Kiến trúc
Mô-đun Cốt lõi
Cơ chế Kiểm soát lỗi
Hiệu năng / Kết quả Thử nghiệm nổi bật
DIN-SQL 14
Liên kết lược đồ, Phân rã câu hỏi, Tạo sinh SQL, Tự sửa lỗi.14
Tự sửa lỗi dựa trên hướng dẫn sửa lỗi chuyên gia viết sẵn.15
Đạt hiệu năng đột phá trên các câu hỏi có độ khó cao của Spider.14
MAC-SQL 14
Tác nhân Chọn lọc (Selector), Tác nhân Phân rã (Decomposer), Tác nhân Tinh chỉnh (Refiner).16
Sử dụng tác nhân Refiner kết hợp kiểm thử và sửa đổi động dựa trên luật cú pháp.16
Đạt độ chính xác thực thi 59.59% trên tập thử nghiệm ẩn của BIRD.16
PExA 13
Hoạch định kế hoạch logic cấp cao, Thực thi mã cấp thấp.13
Phân tích lỗi ngữ nghĩa dựa trên sự sai lệch giữa kế hoạch và cú pháp SQL.13
Đạt độ chính xác thực thi 70.2% trên bộ dữ liệu phức tạp Spider 2.0.13
STaR-SQL 7
Tạo lập lý giải chi tiết (Rationale Generation), Tạo sinh SQL, Bộ kiểm chứng kết quả.7
Sử dụng mô hình phần thưởng giám sát kết quả (ORM) làm bộ lọc xác minh.7
Đạt độ chính xác thực thi vượt trội 86.6% trên bộ dữ liệu Spider.7
X-SQL 14
Liên kết SFT (X-Linking), Giải nghĩa dữ liệu (X-Admin), Điều phối đa LLM (Multi-LLMs).14
Sửa lỗi cú pháp thông qua sự bổ trợ thông tin ngữ cảnh từ mô-đun giải nghĩa dữ liệu.14
Đạt tỷ lệ chính xác cao nhất trên Spider-Dev (84.9%) và Spider-Test (82.5%).14

Tiếp cận RAG và Vai trò của Lớp Ngữ nghĩa
Trong môi trường cơ sở dữ liệu doanh nghiệp quy mô lớn, kỹ thuật Tạo sinh tăng cường tra cứu (RAG) đóng vai trò quyết định trong việc tối ưu hóa lượng thông tin lược đồ truyền vào mô hình.13 Quy trình liên kết lược đồ theo cấu trúc hai giai đoạn (Coarse-to-Fine) bắt đầu bằng việc sử dụng mô hình nhúng để tra cứu thô các bảng ứng viên phù hợp nhất từ kho lưu trữ vector, sau đó sử dụng một LLM chi phí thấp để phân tích sâu cấu trúc của các bảng này nhằm cắt tỉa các cột dư thừa trước khi đưa vào prompt của mô hình sinh SQL chính.13 Phương pháp này giúp tăng độ chính xác thực thi từ 15% đến 20% trên bộ dữ liệu BIRD.13 Đồng thời, các hệ thống tiên tiến sử dụng cơ chế truy xuất dòng dữ liệu (row-level retrievers) để chuyển đổi các giá trị thực tế trong bảng thành vector, giúp mô hình tra cứu ngữ nghĩa chính xác các giá trị cụ thể như tên riêng, mã số thuế hoặc ký tự viết tắt để điền vào điều kiện lọc của câu lệnh SQL.19
Tuy nhiên, tiếp cận Text-to-SQL thô chỉ dựa trên RAG vẫn dễ gặp thất bại khi đối mặt với các thuật ngữ nghiệp vụ không đồng nhất.5 Ví dụ điển hình là câu hỏi về "doanh số tháng trước" sẽ được bộ phận tiếp thị hiểu là tổng giá trị đơn hàng được tạo, bộ phận tài chính hiểu là doanh thu thực nhận, còn bộ phận vận hành lại yêu cầu trừ đi các khoản hoàn trả.21 Để giải quyết triệt để rào cản này, việc xây dựng một Lớp Ngữ nghĩa (Business Semantic Layer) đóng vai trò là cầu nối trừu tượng hóa giữa người dùng và cơ sở dữ liệu vật lý.21 Lớp ngữ nghĩa này mã hóa tri thức kinh doanh, quy tắc tính toán chỉ số và mối quan hệ thực thể dưới dạng một tệp cấu hình có cấu trúc rõ ràng.21
Khi tích hợp với dbt Semantic Layer, LLM không còn tự do viết các câu lệnh SQL thô sơ từ đầu mà chỉ cần biên dịch câu hỏi tự nhiên thành một truy vấn mô tả ngữ nghĩa dựa trên các chiều dữ liệu và chỉ số đã được định nghĩa sẵn.17 Quá trình sinh câu lệnh SQL sau đó diễn ra hoàn toàn deterministic (xác định) thông qua lớp ngữ nghĩa, giúp loại bỏ triệt để nguy cơ viết sai các phép nối bảng phức tạp hoặc sai lệch công thức tính toán chỉ số nghiệp vụ, đưa độ chính xác thực thi tiệm cận mức 100% đối với các truy vấn được lớp ngữ nghĩa hỗ trợ.22
Trong hệ sinh thái Snowflake, công cụ Cortex Analyst ứng dụng một quy trình cải tiến mô hình ngữ nghĩa bằng tác nhân để tự động hóa việc ánh xạ logic.23 Hệ thống vận hành một mạng lưới bao gồm bốn tác nhân chuyên biệt bao gồm tác nhân điều phối (Orchestrator) quản lý toàn bộ luồng công việc, tác nhân quan hệ (Relationships Agent) xác định liên kết bảng tự động dựa trên khóa ngoại và SQL mẫu, tác nhân biên tập mô hình ngữ nghĩa (Semantic Model Editor) tối ưu hóa mô tả các trường thông tin dựa trên lịch sử lỗi truy vấn, và tác nhân viết chỉ dẫn tùy biến (Custom Instruction Editor) để giải quyết các logic nghiệp vụ đặc thù.23 Sự kết hợp này mang lại mức tăng độ chính xác trung bình 20% so với việc chỉ sử dụng một LLM đơn lẻ chạy trên lược đồ thô.23
Khảo sát và So sánh Hệ sinh thái Công cụ Hiện đại
Sự trưởng thành của công nghệ Text-to-SQL đã thúc đẩy sự ra đời của nhiều thư viện và công cụ hỗ trợ mạnh mẽ, giúp rút ngắn thời gian triển khai ứng dụng vào môi trường sản xuất của doanh nghiệp.
Hệ sinh thái LangChain và LangGraph cung cấp một nền tảng vững chắc cho việc xây dựng các tác nhân Text-to-SQL hoạt động theo cơ chế ReAct có trạng thái.24 Thư viện cung cấp bộ công cụ SQLDatabaseToolkit tích hợp sẵn các công cụ như sql_db_list_tables để quét danh sách bảng khả dụng, sql_db_schema để lấy cấu trúc chi tiết và dữ liệu mẫu của bảng, sql_db_query_checker sử dụng một LLM phụ để rà soát lỗi cú pháp trước khi chạy, và công cụ thực thi trực tiếp truy vấn SQL.24 LangGraph cho phép nhà phát triển thiết lập các đồ thị trạng thái phức tạp với các nút chuyên biệt cho từng bước công việc và các cạnh điều kiện để tự động quay lại bước sửa lỗi khi phát hiện ngoại lệ từ cơ sở dữ liệu.25 Điểm vượt trội của LangGraph là khả năng dễ dàng tích hợp cơ chế can thiệp của con người (human-in-the-loop) để dừng luồng chạy tác nhân nhằm kiểm tra hoặc phê duyệt các câu lệnh chỉnh sửa dữ liệu nhạy cảm.25 Khả năng tích hợp này càng trở nên tối ưu khi kết hợp với DuckDB và công cụ xử lý lai MotherDuck để thực thi các truy vấn phân tích quy mô lớn trên đám mây.29
Thư viện LlamaIndex tập trung tối ưu hóa bài toán dưới góc nhìn quản lý dữ liệu và lập chỉ mục cấu trúc.31 Với các cơ sở dữ liệu nhỏ gọn, công cụ NLSQLTableQueryEngine cho phép thực hiện dịch trực tiếp thông qua lược đồ nằm trong prompt.19 Đối với các hệ thống dữ liệu doanh nghiệp lớn, LlamaIndex cung cấp giải pháp SQLTableRetrieverQueryEngine kết hợp với SQLTableNodeMapping và ObjectIndex xây dựng trên kho vector.19 Cơ chế này cho phép hệ thống chỉ lập chỉ mục cho cấu trúc lược đồ của các bảng, sau đó tự động tra cứu ngữ nghĩa và tải các bảng liên quan nhất vào ngữ cảnh tại thời điểm truy vấn.19 Đặc biệt, công cụ PGVectorSQLQueryEngine đóng vai trò là một tính năng thử nghiệm mạnh mẽ hỗ trợ việc suy luận trực tiếp các vector nhúng ngay trong cú pháp của câu lệnh SQL được sinh ra.33
Vanna.ai là một đại diện chuyên biệt vận hành theo triết lý học hỏi liên tục thông qua bộ nhớ vector (Golden Query RAG).17 Khung tác nhân này lưu trữ ba nhóm tri thức cốt lõi bao gồm các câu lệnh DDL định nghĩa cấu trúc bảng, tài liệu mô tả quy tắc kinh doanh và các cặp câu hỏi kèm mã SQL mẫu chuẩn đã xác thực (Golden Queries) vào cơ sở dữ liệu vector.34 Vanna hỗ trợ linh hoạt cả kho vector pgvector được lưu trữ trên đám mây của hãng (VannaDB) lẫn các giải pháp cục bộ như ChromaDB hay Marqo, đồng thời tích hợp đa dạng mô hình từ OpenAI, Anthropic, Gemini cho đến các mô hình cục bộ qua Ollama như Granite hay gpt-oss.37 Việc huấn luyện bộ nhớ được thực hiện dễ dàng thông qua các phương thức vn.add_ddl, vn.add_question_sql, và vn.add_documentation.36
Mặc dù Vanna.ai rất mạnh mẽ, việc ứng dụng công cụ này trong thực tế sản xuất đã bộc lộ nhiều điểm nghẽn kỹ thuật.35 Điều này thúc đẩy sự ra đời của DataChat, một bản phân nhánh tự lưu trữ (self-hosted) được xây dựng trên nền tảng Vanna 2.0 nhằm khắc phục các hạn chế lớn của phiên bản gốc.35 DataChat giải quyết bài toán "chat mù" bằng cách xây dựng một giao diện khám phá cơ sở dữ liệu trực quan giúp người dùng theo dõi lược đồ hiện tại.35 Thay vì quy trình huấn luyện thủ công dễ bị lỗi thời khi cấu trúc bảng thay đổi, DataChat tự động làm mới bối cảnh lược đồ trong ChromaDB tại mỗi thời điểm khởi chạy thông qua tệp cấu hình tự động.35 Bản phân nhánh này cũng loại bỏ sự phức tạp của việc biên dịch giao diện thủ công bằng cơ chế đóng gói một bước, đồng thời khắc phục triệt để các lỗi sập hệ thống khi tuần tự hóa (serialization crashes) các bảng dữ liệu thực tế chứa các kiểu dữ liệu phức tạp như mảng (arrays), trường JSON hoặc nhãn thời gian có múi giờ.35

Thư viện / Công cụ
Cơ chế Quản lý Ngữ cảnh Lược đồ
Mô hình Ngôn ngữ & Cơ sở dữ liệu tương thích
Tính năng Sửa lỗi & Phê duyệt
Ứng dụng Thực tế & Hạn chế
LangChain & LangGraph 24
Sử dụng công cụ quét và tải lược đồ động của bộ công cụ SQLDatabaseToolkit.24
Tương thích đa dạng mô hình thông qua cổng API tiêu chuẩn; kết nối mọi cơ sở dữ liệu hỗ trợ SQLAlchemy.24
Có cơ chế tự sửa lỗi qua ReAct loop; hỗ trợ đầy đủ tính năng phê duyệt thủ công ngắt trạng thái.25
Rất linh hoạt cho các quy trình phức tạp có sự kiểm soát của con người; đòi hỏi chi phí thiết lập hệ thống ban đầu lớn.25
LlamaIndex 19
Lập chỉ mục lược đồ dưới dạng đồ thị thực thể và tra cứu động qua ObjectIndex và SQLTableNodeMapping.19
Hỗ trợ hầu hết LLM thương mại; tích hợp sâu với các kho lưu trữ vector và cơ sở dữ liệu quan hệ, thử nghiệm tốt trên DuckDB.19
Sửa lỗi cơ bản dựa trên bộ máy truy vấn thử lại (Retry Query Engines).33
Tối ưu cho việc tối ưu hóa hiệu năng RAG trên lược đồ cơ sở dữ liệu lớn; luồng tác nhân sửa lỗi chưa linh hoạt bằng LangGraph.25
Vanna.ai 34
Lưu trữ cấu trúc DDL, tài liệu nghiệp vụ và câu lệnh mẫu chuẩn vào cơ sở dữ liệu vector.34
Tương thích với OpenAI, Anthropic, Gemini, Ollama (Granite, gpt-oss); hỗ trợ Snowflake, BigQuery, Postgres, MySQL, SQLite.37
Tự học thông qua phản hồi trong phòng chat và chỉnh sửa của người quản trị.36
Khởi động nhanh nhờ cơ chế Golden Query RAG; gặp rào cản về lược đồ lỗi thời, thiếu giao diện quản trị trực quan và dễ sập khi gặp dữ liệu thực tế phức tạp.17
DataChat 35
Tự động cập nhật lược đồ vào ChromaDB từ cơ sở dữ liệu quan hệ tại mỗi thời điểm khởi chạy.35
Tự đóng gói cùng Vanna 2.0; hỗ trợ kết nối trực tiếp đến máy chủ PostgreSQL và các cơ sở dữ liệu tương tự.35
Kế thừa cơ chế của Vanna 2.0; cải thiện tính ổn định của luồng xử lý lỗi hệ thống.35
Khắc phục hoàn toàn các điểm nghẽn về đồng bộ lược đồ, tuần tự hóa kiểu dữ liệu phức tạp và giao diện sử dụng của Vanna bản gốc.35

Đánh giá Hiệu năng và Thách thức trong Môi trường Thực tế
Việc đo lường và đánh giá năng lực của các hệ thống Text-to-SQL đòi hỏi sự phân biệt rõ ràng giữa các phương pháp tiếp cận học thuật và hiệu năng thực tế tại doanh nghiệp.42 Trong nghiên cứu khoa học, hai chỉ số Exact Match (đánh giá khớp chuỗi tuyệt đối) và Component Match (đánh giá khớp từng phân đoạn cấu trúc) đang dần nhường chỗ cho chỉ số Execution Accuracy (EX) đo lường sự trùng khớp của kết quả dữ liệu đầu ra và chỉ số Valid Efficiency Score (VES) đo lường đồng thời tính đúng đắn và thời gian thực thi của câu lệnh trên các cơ sở dữ liệu quy mô lớn.1
Các bộ dữ liệu mẫu học thuật như Spider từng là tiêu chuẩn vàng để kiểm thử các hệ thống Text-to-SQL đa miền với cấu trúc lồng phức tạp.42 Tuy nhiên, sự ra đời của bộ dữ liệu BIRD đã nâng tiêu chuẩn đánh giá lên tầm cao mới khi tập trung sâu vào quy mô cơ sở dữ liệu lớn (lên tới 33.4 GB) và yêu cầu mô hình phải khai thác tài liệu tri thức nghiệp vụ bổ trợ để tối ưu hiệu suất thực thi thực tế.42
Sự chênh lệch hiệu năng giữa các thí nghiệm học thuật (thường đạt trên 80% hoặc 90% trên Spider) và môi trường triển khai thực tế (sụt giảm nghiêm trọng xuống còn 51% đối với GPT-4o) bắt nguồn từ một phát hiện chấn động về lỗi dán nhãn dữ liệu.42 Nghiên cứu thực nghiệm của Jin và các cộng sự năm 2026 đã chỉ ra rằng tỷ lệ lỗi gán nhãn trong tập phát triển thu gọn của bộ dữ liệu BIRD (BIRD Mini-Dev) lên tới 52.8%, trong khi con số này đối với bộ dữ liệu Spider 2.0-Snow lên tới 66.1%.45 Các lỗi này được phân loại thành bốn mô thức lỗi chính bao gồm:
Mô thức E1 liên quan đến câu hỏi sai lệch hoặc thiếu thông tin cần thiết.
Mô thức E2 liên quan đến việc viết sai câu lệnh SQL chuẩn hoặc đặt câu hỏi tự nhiên mơ hồ, mâu thuẫn là phổ biến nhất, chiếm tới 57.8% lỗi của BIRD Mini-Dev và 55% lỗi của Spider 2.0-Snow.45
Mô thức E3 liên quan đến sự bất khớp về dữ liệu thực tế giữa câu hỏi và cơ sở dữ liệu.
Mô thức E4 liên quan đến các lỗi cú pháp không thể thực thi.
Phát hiện này chứng tỏ các bảng xếp hạng học thuật hiện tại không hoàn toàn phản ánh chính xác năng lực thực tế của các giải pháp công nghệ.45
Một thách thức lớn khác trong môi trường sản xuất thực tế là hiện tượng trôi lệch lược đồ (schema drift) khi cơ sở dữ liệu liên tục tiến hóa theo thời gian qua các phiên bản cập nhật.46 Khảo sát thực tế của các kỹ sư tại hãng Adobe đối với các mô hình Text-to-SQL cho thấy hiệu năng của hệ thống sụt giảm ít nhất 13.3% đối với các cột mới được thêm vào và 9.1% đối với các bảng mới xuất hiện.46 Chi phí đắt đỏ của việc gán nhãn dữ liệu thủ công để tái huấn luyện mô hình đã thúc đẩy việc phát triển hệ thống SQLsynth.46 SQLsynth vận hành như một quy trình gán nhãn dữ liệu có con người tham gia (human-in-the-loop), sử dụng thuật toán ngữ pháp phi ngữ cảnh xác suất (PCFG) để tự động sinh hàng loạt câu lệnh SQL đa dạng từ lược đồ, sau đó dịch ngược lại thành câu hỏi tự nhiên bằng LLM thông qua quá trình phân tích suy luận từng bước nhằm phát hiện lỗi dịch và cho phép người vận hành chỉnh sửa trực quan.46 Quy trình này giúp giảm đáng kể tải nhận thức của kỹ sư và duy trì sự ổn định của hệ thống trước sự biến động lược đồ.46
Để giải quyết triệt để bài toán hiệu năng và chi phí, xu hướng nghiên cứu mới nhất đang tập trung vào kỹ thuật học máy tăng cường căn chỉnh theo kết quả thực thi (Execution-Aligned Reinforcement Learning) trên các mô hình ngôn ngữ nhỏ.47 Dòng mô hình Arctic-Text2SQL-R1 của hãng Snowflake là một bước đột phá lớn khi ứng dụng phương pháp GRPO để huấn luyện mô hình trực tiếp dựa trên phản hồi thực tế từ hệ quản trị cơ sở dữ liệu quan hệ, loại bỏ hoàn toàn các hàm phần thưởng phỏng đoán được viết thủ công.47 Quá trình huấn luyện sử dụng các bộ dữ liệu được sàng lọc kỹ lưỡng để loại bỏ các truy vấn rác không tạo ra kết quả hoặc tốn quá nhiều thời gian thực thi.47
Kết quả thực nghiệm cho thấy mô hình Arctic-Text2SQL-R1-32B đạt độ chính xác thực thi vượt trội lên tới 71.83% trên bộ dữ liệu BIRD, trong khi phiên bản nhỏ gọn Arctic-Text2SQL-R1-14B đạt 70.04% và phiên bản Arctic-Text2SQL-R1-7B dù có dung lượng tham số nhỏ hơn 95 lần vẫn đạt độ chính xác 68.47%, tương đương với hiệu năng của mô hình ExCoT-70B khổng lồ và vượt xa nhiều giải pháp thương mại đắt đỏ.47 Định hướng công nghệ này hứa hẹn sẽ tối ưu hóa chi phí vận hành, bảo mật thông tin nội bộ doanh nghiệp và nâng cao tính tin cậy của các giải pháp Text-to-SQL trong kỷ nguyên đại công nghiệp dữ liệu.11

Tên bộ dữ liệu (Benchmark)
Quy mô & Dung lượng dữ liệu
Đặc điểm cấu trúc câu lệnh
Thách thức lớn nhất
Tỷ lệ lỗi gán nhãn được phát hiện
WikiSQL (2017) 42
Lớn (80,000+ cặp câu hỏi-SQL, 25,000+ bảng từ Wikipedia) 42
Cực kỳ đơn giản; chủ yếu truy vấn trên một bảng duy nhất, không có phép nối (JOIN) 42
Độ phức tạp thấp, không phản ánh đúng thực tế cơ sở dữ liệu quan hệ 42
Không có báo cáo chi tiết trong nghiên cứu hiện tại.
Spider (2018) 42
Trung bình (10,181 truy vấn, 138 miền dữ liệu khác nhau) 42
Độ phức tạp từ trung bình đến rất cao; lồng ghép nhiều phép JOIN, GROUP BY, HAVING 42
Đánh giá khả năng tổng quát hóa đa miền nhưng lược đồ vẫn mang tính học thuật sạch sẽ 42
66.1% (Đối với phiên bản Spider 2.0-Snow) 45
KaggleDBQA (2021) 42
Nhỏ; xây dựng từ các cơ sở dữ liệu thực tế trên nguồn Kaggle 42
Phức tạp vừa phải; kết hợp tài liệu mô tả dữ liệu và siêu dữ liệu thực tế 42
Yêu cầu khả năng đọc hiểu và khai thác tài liệu bổ trợ để viết SQL chính xác 42
Không có báo cáo chi tiết trong nghiên cứu hiện tại.
BIRD (2024) 42
Rất lớn (12,751 truy vấn, 95 cơ sở dữ liệu, tổng dung lượng 33.4 GB) 42
Phức tạp cao; tối ưu hóa hiệu suất chạy truy vấn và khai thác bằng chứng tri thức ngoài 42
Cơ sở dữ liệu quy mô lớn, yêu cầu tối ưu hóa tốc độ chạy lệnh (VES) 42
52.8% (Đối với tập BIRD Mini-Dev) 45

Nguồn trích dẫn
Large Language Model Enhanced Text-to-SQL Generation: A Survey - arXiv, truy cập vào tháng 5 26, 2026, <https://arxiv.org/html/2410.06011v1>
NLI4DB: A Systematic Review of Natural Language Interfaces for Databases - arXiv, truy cập vào tháng 5 26, 2026, <https://arxiv.org/html/2503.02435v1>
Natural Language to SQL: A Semantic Mapping and Metadata Approach for Database Interaction - Atlantis Press, truy cập vào tháng 5 26, 2026, <https://www.atlantis-press.com/article/126017346.pdf>
Interactive Natural Language Interface - WSEAS US, truy cập vào tháng 5 26, 2026, <https://www.wseas.us/e-library/transactions/computers/2009/29-134.pdf>
Traditional Text-to-SQL (No Semantic Layer) vs. Semantics-Driven Text-to-SQL | by Dr. Sanjay Kumar, truy cập vào tháng 5 26, 2026, <https://skphd.medium.com/traditional-text-to-sql-no-semantic-layer-vs-semantics-driven-text-to-sql-5be57bb2f6e2>
(PDF) The Lunar Sciences Natural Language Information System - ResearchGate, truy cập vào tháng 5 26, 2026, <https://www.researchgate.net/publication/24285293_The_Lunar_Sciences_Natural_Language_Information_System>
STaR-SQL: Self-Taught Reasoner for Text-to-SQL - arXiv, truy cập vào tháng 5 26, 2026, <https://arxiv.org/html/2502.13550v1>
SQL-of-Thought: Multi-agentic Text-to-SQL with Guided Error Correction - arXiv, truy cập vào tháng 5 26, 2026, <https://arxiv.org/html/2509.00581v1>
A robust natural language text-to-SQL generation framework with dynamic strategies based on LLMs - PMC, truy cập vào tháng 5 26, 2026, <https://pmc.ncbi.nlm.nih.gov/articles/PMC12953869/>
Next-Generation Database Interfaces: A Survey of LLM-based Text-to-SQL - arXiv, truy cập vào tháng 5 26, 2026, <https://arxiv.org/html/2406.08426v3>
Next-Generation Database Interfaces: A Survey of LLM-based Text-to-SQL - arXiv, truy cập vào tháng 5 26, 2026, <https://arxiv.org/html/2406.08426v8>
A Survey of Text-to-SQL in the Era of LLMs: Where are we, and where are we going? - arXiv, truy cập vào tháng 5 26, 2026, <https://arxiv.org/html/2408.05109v5>
Architecting State-of-the-Art Text-to-SQL Agents for Enterprise ..., truy cập vào tháng 5 26, 2026, <https://pub.towardsai.net/architecting-state-of-the-art-text-to-sql-agents-for-enterprise-complexity-629c5c5197b8>
X-SQL: Expert Schema Linking and Understanding of Text-to-SQL with Multi-LLMs - arXiv, truy cập vào tháng 5 26, 2026, <https://arxiv.org/html/2509.05899v1>
MAGIC: Generating Self-Correction Guideline for In-Context Text-to-SQL - AAAI Publications, truy cập vào tháng 5 26, 2026, <https://ojs.aaai.org/index.php/AAAI/article/view/34511/36666>
MAC-SQL: A Multi-Agent Collaborative Framework for Text-to-SQL - ACL Anthology, truy cập vào tháng 5 26, 2026, <https://aclanthology.org/2025.coling-main.36.pdf>
AI Dashboard: How to move from 80% to 95% Text-to-SQL accuracy? (Vanna vs. Custom Agentic RAG : r/LangChain - Reddit, truy cập vào tháng 5 26, 2026, <https://www.reddit.com/r/LangChain/comments/1rljy67/ai_dashboard_how_to_move_from_80_to_95_texttosql/>
ow to move from 80% to 95% Text-to-SQL accuracy? (Vanna vs. Custom Agentic RAG) - Reddit, truy cập vào tháng 5 26, 2026, <https://www.reddit.com/r/Rag/comments/1rlk3ad/ow_to_move_from_80_to_95_texttosql_accuracy_vanna/>
Text-to-SQL Guide (Query Engine + Retriever) | Developer Documentation - LlamaParse, truy cập vào tháng 5 26, 2026, <https://developers.llamaindex.ai/python/examples/index_structs/struct_indices/sqlindexdemo/>
Semantic Parsing for Text-to-SQL in BI - Querio, truy cập vào tháng 5 26, 2026, <https://querio.ai/articles/semantic-parsing-for-text-to-sql-in-bi>
What is a Text-to-SQL Business Semantic Layer? Why is it the Key to AI Query Accuracy?, truy cập vào tháng 5 26, 2026, <https://www.asktable.com/en-US/articles/2026-01-20/text-to-sql-semantic-layer-explained>
Semantic Layer vs. Text-to-SQL: 2026 Benchmark Update | dbt Developer Blog, truy cập vào tháng 5 26, 2026, <https://docs.getdbt.com/blog/semantic-layer-vs-text-to-sql-2026>
Agentic Semantic Model Improvement: Elevating Text-to-SQL Performance - Snowflake, truy cập vào tháng 5 26, 2026, <https://www.snowflake.com/en/blog/engineering/agentic-semantic-model-text-to-sql/>
langchain-ai/text-to-sql-agent - GitHub, truy cập vào tháng 5 26, 2026, <https://github.com/langchain-ai/text-to-sql-agent>
Build a custom SQL agent - Docs by LangChain, truy cập vào tháng 5 26, 2026, <https://docs.langchain.com/oss/python/langgraph/sql-agent>
toolkit | langchain_community - LangChain Reference Docs, truy cập vào tháng 5 26, 2026, <https://reference.langchain.com/python/langchain-community/agent_toolkits/sql/toolkit>
SQL Agent with Cohere and LangChain (i-5O Case Study), truy cập vào tháng 5 26, 2026, <https://docs.cohere.com/page/sql-agent-cohere-langchain>
Build a SQL agent - Docs by LangChain, truy cập vào tháng 5 26, 2026, <https://docs.langchain.com/oss/python/langchain/sql-agent>
Tutorial: How to build a LangChain text-to-SQL agent that can automatically recover from bad SQL - Reddit, truy cập vào tháng 5 26, 2026, <https://www.reddit.com/r/LangChain/comments/1sgqcii/tutorial_how_to_build_a_langchain_texttosql_agent/>
Building a Text-to-SQL Agent with DuckDB, MotherDuck and LangChain, truy cập vào tháng 5 26, 2026, <https://motherduck.com/blog/langchain-sql-agent-duckdb-motherduck/>
SQL Query Engine with LlamaIndex + DuckDB | Developer Documentation - LlamaParse, truy cập vào tháng 5 26, 2026, <https://developers.llamaindex.ai/python/examples/index_structs/struct_indices/duckdb_sql_query/>
Structured Data | Developer Documentation - LlamaParse, truy cập vào tháng 5 26, 2026, <https://developers.llamaindex.ai/python/framework/understanding/putting_it_all_together/structured_data/>
SQL table retriever - LlamaIndex, truy cập vào tháng 5 26, 2026, <https://developers.llamaindex.ai/python/framework-api-reference/query_engine/SQL_table_retriever/>
Documentation - Vanna AI, truy cập vào tháng 5 26, 2026, <https://vanna.ai/docs>
I Turned an Archived 23K-Star Text-to-SQL Project Into a Self-Hosted Tool That Actually Works Out of the Box | by Harun Yuksel - Towards AI, truy cập vào tháng 5 26, 2026, <https://pub.towardsai.net/i-turned-an-archived-23k-star-text-to-sql-project-into-a-self-hosted-tool-that-actually-works-out-b08abcb6d0e3>
Training - Vanna AI Docs, truy cập vào tháng 5 26, 2026, <https://vanna.ai/docs/placeholder/training>
Vanna AI, truy cập vào tháng 5 26, 2026, <https://vanna.ai/>
How to Use Vanna.ai to Query Your Database with Open-Source Language Models, truy cập vào tháng 5 26, 2026, <https://dev.to/aairom/how-to-use-vannaai-to-query-your-database-with-open-source-language-models-5ado>
Generating SQL for Other Database using Other LLM, Vanna Hosted Vector DB (Recommended), truy cập vào tháng 5 26, 2026, <https://try.vanna.ai/docs/other-database-other-llm-vannadb/>
The Base Class - Vanna.AI Documentation, truy cập vào tháng 5 26, 2026, <https://ask.vanna.ai/docs/base/>
Build a SQL agent - Docs by LangChain, truy cập vào tháng 5 26, 2026, <https://docs.langchain.com/oss/javascript/langchain/sql-agent>
Benchmarking the Text-to-SQL Capability of Large Language Models: A Comprehensive Evaluation - arXiv, truy cập vào tháng 5 26, 2026, <https://arxiv.org/html/2403.02951v2>
Snowflake Cortex Analyst: Evaluating Text-to-SQL Accuracy for Real-World BI, truy cập vào tháng 5 26, 2026, <https://www.snowflake.com/en/blog/engineering/cortex-analyst-text-to-sql-accuracy-bi/>
From Natural Language to SQL: Review of LLM-based Text-to-SQL Systems - arXiv, truy cập vào tháng 5 26, 2026, <https://arxiv.org/html/2410.01066v1>
Text-to-SQL Benchmarks are Broken: An In-Depth Analysis of Annotation Errors - VLDB Endowment, truy cập vào tháng 5 26, 2026, <https://www.vldb.org/cidrdb/papers/2026/p5-jin.pdf>
Text-to-SQL Domain Adaptation via Human-LLM Collaborative Data Annotation - arXiv, truy cập vào tháng 5 26, 2026, <https://arxiv.org/html/2502.15980v1>
Smaller Models, Smarter SQL: Arctic-Text2SQL-R1 Tops BIRD and Wins Broadly, truy cập vào tháng 5 26, 2026, <https://www.snowflake.com/en/blog/engineering/arctic-text2sql-r1-sql-generation-benchmark/>
