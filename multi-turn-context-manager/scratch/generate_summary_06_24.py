import csv
import json
import os
import re

# File paths
test_summary_in = r"D:\VJ\Tro-li-ao-Javis\multi-turn-context-manager\reports\tests\test_summary_06_22.csv"
test_summary_out = r"D:\VJ\Tro-li-ao-Javis\multi-turn-context-manager\reports\tests\test_summary_06_24.csv"
v4_json_path = r"D:\VJ\Tro-li-ao-Javis\multi-turn-context-manager\test_results_v4.json"

# Load JSON results
with open(v4_json_path, 'r', encoding='utf-8') as f:
    v4_results = json.load(f)

v4_results_map = {r['test_id']: r for r in v4_results}

# V4 scenario metadata
v4_scenarios = [
    {
        "test_id": "H1_WEB_SIMULATED_URL",
        "category": "Standard",
        "total_turns": 1,
        "queries": [
            ("ネットで最新のAIニュースについて検索して、関係する記事のURLを含めて要約してください。",
             "Hãy tìm kiếm tin tức AI mới nhất trên mạng và tóm tắt kèm theo URL của các bài viết liên quan.")
        ],
        "expected": "T1: Kết quả định tuyến sang WEB pipeline và tóm tắt chứa các URL mô phỏng",
        "tech_val": "Định tuyến WEB pipeline, xác thực định dạng URL và thông tin trong câu trả lời từ công cụ tìm kiếm",
        "func_val": "Kiểm tra khả năng định tuyến đúng sang WEB pipeline khi phát hiện từ khóa tìm kiếm và khả năng xử lý/trình bày URL tin tức một cách chính xác."
    },
    {
        "test_id": "H2_FAIL_OPEN_WARNING",
        "category": "FIX",
        "total_turns": 1,
        "queries": [
            ("GT_03の島田さんは何を希望していましたか？",
             "Shimada-san trong cuộc gọi GT_03 mong muốn điều gì?")
        ],
        "expected": "T1: Phản hồi từ hệ thống kèm theo cảnh báo từ chối trách nhiệm (cảnh báo Engine kiểm tra độ tin cậy ngoại tuyến)",
        "tech_val": "Cơ chế Fail-Open và cảnh báo tự động khi Engine tự kiểm tra ảo giác bị lỗi/timeout",
        "func_val": "Xác nhận rằng khi Engine kiểm tra ảo giác gặp ngoại lệ, hệ thống không bị treo (fail-open) và tự động đính kèm cảnh báo tính toàn vẹn vào phản hồi."
    },
    {
        "test_id": "H3_DOUBLE_PRONOUN_REPLACEMENT",
        "category": "Standard",
        "total_turns": 1,
        "queries": [
            ("彼がそれについて気にした理由は何ですか？",
             "Lý do anh ấy quan tâm đến điều đó là gì?")
        ],
        "expected": "T1: Cả hai đại từ '彼' và 'それ' được phân giải chính xác (ví dụ: Shimada và việc xem nhà)",
        "tech_val": "Thay thế đại từ kép (彼 -> Shimada-san, それ -> nội dung xem nhà/vấn đề) trong cùng một lượt hội thoại",
        "func_val": "Kiểm tra khả năng phân giải đồng thời nhiều đại từ phức tạp trong một câu hỏi để tránh định tuyến sai hoặc bỏ sót ngữ cảnh."
    },
    {
        "test_id": "H4_CACHE_TTL_STALE_FILTER",
        "category": "NEG",
        "total_turns": 1,
        "queries": [
            ("その時の詳しい内容を教えてください。",
             "Cho biết chi tiết về thời điểm đó.")
        ],
        "expected": "T1: Không sử dụng cache cũ đã hết hạn (quá 24 giờ), kích hoạt truy vấn mới hoàn toàn",
        "tech_val": "Lọc và bỏ qua cache hết hạn (TTL stale context filtering), bắt buộc truy xuất dữ liệu mới",
        "func_val": "Đảm bảo hệ thống không dùng lại thông tin lỗi thời trong cache khi đã quá hạn thời gian hiệu lực, tránh việc trả về dữ liệu cũ."
    },
    {
        "test_id": "H5_ROLE_REVERSAL_CHECK",
        "category": "NEG",
        "total_turns": 1,
        "queries": [
            ("GT_07の通話で、誰から誰に電話をかけましたか？発信側と受信側を明確にして答えてください。",
             "Trong cuộc gọi GT_07, ai đã gọi cho ai? Hãy làm rõ bên gọi và bên nhận.")
        ],
        "expected": "T1: Xác định đúng Yamashita là người gọi (phát sinh) và receptionist/Maruken (hoặc Ishihara) là người nhận",
        "tech_val": "Chống đảo ngược vai trò thoại (Role reversal prevention) dựa trên cấu trúc câu chào và ngữ cảnh cuộc gọi",
        "func_val": "Đánh giá khả năng phân tích hội thoại để xác định chính xác ai là người chủ động gọi và ai là người nhận cuộc gọi, không bị nhầm lẫn bởi các câu chào hỏi."
    },
    {
        "test_id": "H6_DIRECT_PATH_REASONING_BYPASS",
        "category": "SQL",
        "total_turns": 1,
        "queries": [
            ("GT_03とGT_09の通話時間の合計秒数について、その計算が正しい理由と背景を解説してください。",
             "Hãy giải thích lý do và bối cảnh tại sao phép tính tổng thời lượng cuộc gọi GT_03 và GT_09 lại chính xác.")
        ],
        "expected": "T1: Bỏ qua đường dẫn phản hồi trực tiếp (direct path) và sinh lời giải thích chi tiết thông qua LLM generator",
        "tech_val": "Tự động bỏ qua đường dẫn trực tiếp (Direct-path bypass) đối với các câu hỏi yêu cầu lập luận logic/giải thích",
        "func_val": "Đảm bảo hệ thống sử dụng LLM để giải thích các phép toán/logic thay vì trả về các kết quả thô có sẵn từ database."
    },
    {
        "test_id": "H7_CONCURRENT_SESSION_LOCK_TIMEOUT",
        "category": "Stress",
        "total_turns": 1,
        "queries": [
            ("Simulating concurrent request advisory lock timeout",
             "Mô phỏng timeout khóa Advisory Lock cho các truy vấn đồng thời")
        ],
        "expected": "T1: Hệ thống nâng lên ngoại lệ asyncio.TimeoutError khi không giành được khóa trong thời gian quy định",
        "tech_val": "Quản lý khóa đồng thời cấp session (Advisory Lock timeout) để tránh deadlock",
        "func_val": "Kiểm tra cơ chế xử lý tranh chấp tài nguyên khi nhiều yêu cầu đồng thời truy cập cùng một session, bảo đảm hệ thống từ chối/hết giờ thay vì treo."
    },
    {
        "test_id": "H8_CIRCUIT_BREAKER_TRANSITIONS",
        "category": "FIX",
        "total_turns": 1,
        "queries": [
            ("Simulating circuit breaker state transitions (CLOSED->OPEN->HALF_OPEN->CLOSED)",
             "Mô phỏng chuyển đổi trạng thái Circuit Breaker (CLOSED->OPEN->HALF_OPEN->CLOSED)")
        ],
        "expected": "T1: Trạng thái ngắt mạch chuyển đổi chính xác và kích hoạt phản hồi dự phòng (fallback) khi bị lỗi liên tiếp",
        "tech_val": "Kiểm tra máy trạng thái của Circuit Breaker cho database/LLM engine",
        "func_val": "Xác nhận hệ thống có khả năng tự ngắt và hồi phục khi một dịch vụ phụ trợ liên tục gặp sự cố, đảm bảo tính sẵn sàng cao."
    },
    {
        "test_id": "H9_WEB_RELEVANCE_AND_FALLBACK",
        "category": "Standard",
        "total_turns": 1,
        "queries": [
            ("Testing should_use_direct_path for WEB pipeline",
             "Kiểm tra hàm should_use_direct_path cho luồng WEB")
        ],
        "expected": "T1: Kết quả trả về đúng (A=True, B=False, C=False, D=False) theo quy tắc độ liên quan và số lượng kết quả",
        "tech_val": "Đánh giá logic quyết định direct path đối với dữ liệu từ luồng WEB",
        "func_val": "Bảo đảm luồng Web chỉ phản hồi trực tiếp khi có duy nhất 1 kết quả cực kỳ liên quan, ngược lại phải qua LLM generator."
    },
    {
        "test_id": "H10_GENDER_AWARE_PRONOUN_RESOLUTION",
        "category": "Standard",
        "total_turns": 1,
        "queries": [
            ("Routing masculine vs feminine pronouns to gender-classified participants",
             "Định tuyến đại từ nam/nữ tới các bên tham gia được phân loại giới tính")
        ],
        "expected": "T1: '彼' phân giải thành Sato Taro | T2: '彼女' phân giải thành Suzuki Hanako",
        "tech_val": "Phân giải đại từ theo giới tính (Gender-aware pronoun resolution) dựa trên siêu dữ liệu người tham gia",
        "func_val": "Đảm bảo hệ thống phân biệt được giới tính của các nhân vật khi phân giải đại từ để thay thế chính xác tên người nói."
    },
    {
        "test_id": "H11_CACHE_EMPTY_PAYLOAD_DOWNGRADE",
        "category": "FIX",
        "total_turns": 1,
        "queries": [
            ("島田さんについての詳細な内容を教えてください。",
             "Hãy cho tôi biết thông tin chi tiết về Shimada-san.")
        ],
        "expected": "T1: Cache trống bị hạ cấp thành yêu cầu truy xuất đầy đủ (needs_retrieval='full')",
        "tech_val": "Phát hiện payload cache rỗng và hạ cấp (Cache downgrade) để tránh trả về câu trả lời rỗng hoặc lỗi",
        "func_val": "Đảm bảo khi cache tồn tại nhưng không có nội dung hữu ích, hệ thống sẽ thực hiện truy xuất dữ liệu mới thay vì trả về kết quả rỗng."
    },
    {
        "test_id": "H12_CACHE_GRANULARITY_DETAILS_UPGRADE",
        "category": "FIX",
        "total_turns": 1,
        "queries": [
            ("島田さんの具体的な発言内容を教えてください。",
             "Hãy cho tôi biết nội dung phát ngôn cụ thể của Shimada-san.")
        ],
        "expected": "T1: Nâng cấp yêu cầu truy xuất lên 'full' do cache thiếu chi tiết mức hội thoại thoại",
        "tech_val": "Nâng cấp truy xuất (Cache granularity upgrade) khi câu hỏi yêu cầu mức độ chi tiết cao hơn cache hiện tại",
        "func_val": "Ngăn ngừa lỗi mất thông tin chi tiết bằng cách tự động bỏ qua cache tóm tắt/metadata khi người dùng hỏi sâu về phát ngôn trực tiếp."
    },
    {
        "test_id": "H13_CROSS_POLLINATION_HALT",
        "category": "NEG",
        "total_turns": 1,
        "queries": [
            ("GT_03の横堀さんはアセットジャパンに何の目的で連絡しましたか？",
             "Yokobori-san trong GT_03 đã liên lạc với Asset Japan nhằm mục đích gì?")
        ],
        "expected": "T1: Từ chối liên kết Yokobori với GT_03 và chỉ rõ Yokobori thuộc cuộc gọi GT_04",
        "tech_val": "Chặn nhiễm chéo thực thể giữa các session (Cross-pollination halt / Hallucination Trap)",
        "func_val": "Bảo vệ hệ thống khỏi việc kết hợp sai lệch thông tin giữa các cuộc gọi khác nhau, phát hiện ra bẫy thực thể không khớp."
    },
    {
        "test_id": "H14_ABSENT_ACTOR_HALLUCINATION_TRAP",
        "category": "NEG",
        "total_turns": 1,
        "queries": [
            ("GT_04で中原凛花さんは、いつ折り返しの電話をかけると言っていましたか？",
             "Trong cuộc gọi GT_04, Nakahara Rinka nói cô ấy sẽ gọi lại vào lúc nào?")
        ],
        "expected": "T1: Phản hồi rõ Nakahara Rinka vắng mặt (nghỉ phép) và không có phát ngôn nào trong cuộc gọi",
        "tech_val": "Phát hiện thực thể vắng mặt (Absent actor / Identity Hallucination Trap)",
        "func_val": "Ngăn chặn việc gán lời thoại của người khác cho nhân vật vắng mặt, tránh bị lừa bởi câu hỏi giả định sai thực tế."
    },
    {
        "test_id": "H15_OUT_OF_CONTEXT_COMPANY_INFO_REFUSAL",
        "category": "NEG",
        "total_turns": 1,
        "queries": [
            ("アセットジャパン of 2026年現在の代表取締役社長の名前を教えてください。",
             "Hãy cho tôi biết tên của Giám đốc đại diện kiêm Chủ tịch hiện tại của Asset Japan vào năm 2026.")
        ],
        "expected": "T1: Từ chối trả lời do thông tin nằm ngoài ngữ cảnh (Out-of-context refusal)",
        "tech_val": "Chặn ảo giác tham số (Parametric hallucination prevention) đối với thông tin ngoài cơ sở dữ liệu",
        "func_val": "Bảo đảm AI không tự bịa ra thông tin doanh nghiệp (như tên giám đốc) khi thông tin đó hoàn toàn không có trong tài liệu cuộc gọi."
    },
    {
        "test_id": "H16_VERIFIER_CORRECTION_LOOP",
        "category": "FIX",
        "total_turns": 1,
        "queries": [
            ("GT_03 of 島田さんは何の内見を希望していましたか？",
             "Shimada-san trong GT_03 muốn xem (nội thất) căn nhà nào?")
        ],
        "expected": "T1: Phát hiện câu trả lời ảo giác ban đầu (10 tỷ Yên), kích hoạt vòng lặp sửa lỗi và trả về câu trả lời chính xác",
        "tech_val": "Vòng lặp sửa lỗi tự động với Engine kiểm tra ảo giác (Self-check correction loop)",
        "func_val": "Kiểm tra tính đúng đắn của vòng lặp tự sửa sai: khi Engine phát hiện câu trả lời đầu tiên bị ảo giác, nó phải sửa lại cho đúng."
    }
]

def main():
    rows = []
    # Read existing CSV (V1, V2, V3)
    with open(test_summary_in, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        rows.append(header)
        for row in reader:
            if row:
                rows.append(row)
    
    # Process V4 Scenarios
    for sc in v4_scenarios:
        test_id = sc["test_id"]
        res = v4_results_map.get(test_id)
        
        if not res:
            print(f"Warning: Test ID {test_id} not found in test results!")
            continue
            
        status = "PASS" if res.get("passed", False) else "FAIL"
        ans = res.get("answer", "")
        
        # Clean answer formatting
        ans_clean = ans.replace("\n", "  ").replace('"', "'")
        
        # Special format for H10
        if test_id == "H10_GENDER_AWARE_PRONOUN_RESOLUTION":
            # T1: He rewrite: ... | T2: She rewrite: ...
            actual = ans_clean.replace("He rewrite:", "T1: He rewrite:").replace(", She rewrite:", " | T2: She rewrite:")
        else:
            actual = f"T1: {ans_clean}"
            
        japanese_parts = []
        vietnamese_parts = []
        for idx, (jp_q, vi_q) in enumerate(sc["queries"]):
            turn_id = f"T{idx+1}"
            japanese_parts.append(f"{turn_id}: {jp_q}")
            vietnamese_parts.append(f"{turn_id}: {vi_q}")
            
        japanese_flow = " | ".join(japanese_parts)
        vietnamese_flow = " | ".join(vietnamese_parts)
        
        rows.append([
            "V4",
            sc["category"],
            sc["test_id"],
            str(sc["total_turns"]),
            japanese_flow,
            vietnamese_flow,
            status,
            sc["expected"],
            actual,
            "",  # Translation will be populated by translation script
            sc["tech_val"],
            sc["func_val"]
        ])
        
    # Write updated rows to test_summary_06_24.csv
    with open(test_summary_out, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(rows)
        
    print(f"Successfully generated: {test_summary_out}")

if __name__ == "__main__":
    main()
