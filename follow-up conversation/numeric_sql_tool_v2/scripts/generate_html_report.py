import sys
import json
import re
import asyncio
from pathlib import Path
import pandas as pd
from datetime import date
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

# Comprehensive translations dictionary
seeds = {
    "5月26日の会議は何について話し合いましたか？": "Cuộc họp ngày 26 tháng 5 đã thảo luận về vấn đề gì?",
    "5月26日の定例会議で議論された主な議題は何ですか？": "Các chủ đề thảo luận chính trong cuộc họp định kỳ ngày 26 tháng 5 là gì?",
    "5月26日の会議で、第2四半期の予算はいくらでしたか？": "Trong cuộc họp ngày 26 tháng 5, ngân sách quý 2 là bao nhiêu?",
    "5月26日の会議で第2四半期の予算について発言したのは誰ですか？": "Ai đã phát biểu về ngân sách quý 2 trong cuộc họp ngày 26 tháng 5?",
    "音声認識プロジェクトについて話し合われた会議はいつですか？": "Cuộc họp thảo luận về dự án nhận dạng giọng nói diễn ra khi nào?",
    "今月は会議が何回ありますか？": "Tháng này có bao nhiêu cuộc họp?",
    "私が参加した会議のうち、最も長かった会議はいつですか？": "Trong số các cuộc họp tôi tham gia, cuộc họp dài nhất là khi nào?",
    "佐藤さんは5月26日の会議で、第2四半期の予算について何分頃に発言しましたか？": "Sato đã phát biểu về ngân sách quý 2 vào khoảng phút thứ mấy trong cuộc họp ngày 26 tháng 5?",
    "昨日、何か会議はありましたか？": "Hôm qua có cuộc họp nào không?",
    "2026年5月に記録された会議は全部で何件ですか？": "Tổng cộng có bao nhiêu cuộc họp được ghi nhận vào tháng 5 năm 2026?",
    "5月15日の会議の所要時間は何秒ですか？": "Thời lượng cuộc họp ngày 15 tháng 5 là bao nhiêu giây?",
    "5月20日の営業レビュー会議は何件カウントされますか？": "Có bao nhiêu cuộc họp đánh giá kinh doanh ngày 20 tháng 5 được tính?",
    "予算の話があった会議は何件ありますか？": "Có bao nhiêu cuộc họp nói về vấn đề ngân sách?",
    "AiVoice Proのローンチについて話した会議を教えてください。": "Hãy cho tôi biết những cuộc họp nói về việc ra mắt AiVoice Pro.",
    "話者ごとに、今月の会議数を集計してください。": "Hãy thống kê số lượng cuộc họp trong tháng này theo từng người nói.",
    "日ごとの会議件数を教えてください。今月でお願いします。": "Hãy cho biết số lượng cuộc họp theo từng ngày trong tháng này.",
    "今週の合計会議時間は何秒ですか？": "Tổng thời gian họp tuần này là bao nhiêu giây?",
    "先月の平均会議時間を教えてください。": "Hãy cho biết thời gian họp trung bình tháng trước.",
    "一番短かった会議はどの日ですか？": "Cuộc họp ngắn nhất là vào ngày nào?",
    "2026-05-26의会議はありますか？": "Có cuộc họp ngày 2026-05-26 không?",
    "2026-05-26の会議はありますか？": "Có cuộc họp ngày 2026-05-26 không?",
    "記録されている会議はありますか？": "Có cuộc họp nào được ghi nhận không?",
    "今月の会議データはありますか？": "Có dữ liệu cuộc họp nào trong tháng này không?",
    "先週の会議記録は存在しますか？": "Bản ghi cuộc họp tuần trước có tồn tại không?",
    "一番長い会議は何秒でしたか？": "Cuộc họp dài nhất kéo dài bao nhiêu giây?",
    "最も短い会議の所要時間は？": "Thời lượng của cuộc họp ngắn nhất là bao nhiêu?",
    "今月の会議の合計時間は？": "Tổng thời gian họp trong tháng này là bao nhiêu?",
    "先月の平均的な会議の長さは？": "Thời lượng họp trung bình trong tháng trước là bao nhiêu?",
    "会議の総数を教えてください。": "Hãy cho biết tổng số lượng cuộc họp.",
    "今月の会議の数は？": "Số lượng cuộc họp trong tháng này là bao nhiêu?",
    "先週、いくつ会議がありましたか？": "Tuần trước đã có bao nhiêu cuộc họp?",
    "今月の全会議の合計時間は何秒ですか？": "Tổng thời gian họp của tất cả cuộc họp tháng này là bao nhiêu giây?",
    "先月の会議時間の合計を教えてください。": "Hãy cho biết tổng thời gian họp tháng trước.",
    "今週の合計会議時間を教えてください。": "Hãy cho biết tổng thời gian họp tuần này.",
    "先週の平均会議時間は何秒ですか？": "Thời gian họp trung bình tuần trước là bao nhiêu giây?",
    "今月の平均会議時間を教えてください。": "Hãy cho biết thời gian họp trung bình tháng này.",
    "最も長かった会議は何秒ですか？": "Cuộc họp dài nhất là bao nhiêu giây?",
    "最も短い会議はどれですか？": "Cuộc họp ngắn nhất là cuộc họp nào?",
    "一番長い会議を教えてください。": "Hãy cho biết cuộc họp dài nhất.",
    "今月で一番短かった会議はどれですか？": "Cuộc họp ngắn nhất trong tháng này là cuộc họp nào?",
    "全会議の所要時間の合計は？": "Tổng thời lượng của tất cả cuộc họp là bao nhiêu?",
    "話者ごとの会議数を教えてください。": "Hãy cho biết số lượng cuộc họp theo từng người nói.",
    "話者別に会議件数を集計してください。": "Hãy thống kê số lượng cuộc họp theo từng người nói.",
    "日ごとの会議件数を教えてください。": "Hãy cho biết số lượng cuộc họp theo từng ngày.",
    "日別の会議数を集計してください。": "Hãy thống kê số lượng cuộc họp theo từng ngày.",
    "話者ごとの合計会議時間を教えてください。": "Hãy cho biết tổng thời gian họp theo từng người nói.",
    "日ごとの合計会議時間を教えてください。": "Hãy cho biết tổng thời gian họp theo từng ngày.",
    "話者ごとの平均会議時間は？": "Thời gian họp trung bình theo từng người nói là bao nhiêu?",
    "話者別の会議件数はどうなっていますか？": "Số lượng cuộc họp theo từng người nói là bao nhiêu?",
    "日ごとに何件の会議がありましたか？": "Có bao nhiêu cuộc họp mỗi ngày?",
    "日別に会議時間を集計してください。": "Hãy thống kê thời gian họp theo từng ngày.",
    "今日の会議の合計時間は？": "Tổng thời gian họp hôm nay là bao nhiêu?",
    "昨日の合計会議時間は何秒ですか？": "Tổng thời gian họp hôm qua là bao nhiêu giây?",
    "明日の会議は記録されていますか？": "Cuộc họp ngày mai có được ghi lại không?",
    "先週の会議件数と合計時間は？": "Số lượng cuộc họp và tổng thời gian họp tuần trước là bao nhiêu?",
    "来月の会議は何件ありますか？": "Có bao nhiêu cuộc họp vào tháng sau?",
    "来週の会議は記録されていますか？": "Cuộc họp tuần sau có được ghi lại không?",
    "2026-05-15の会議は何件ですか？": "Có bao nhiêu cuộc họp vào ngày 15/05/2026?",
    "2026-05-20の会議の所要時間は？": "Thời lượng cuộc họp ngày 20/05/2026 là bao nhiêu?",
    "2026-05-15から2026-05-26の会議は何件ありますか？": "Có bao nhiêu cuộc họp từ ngày 15/05/2026 đến ngày 26/05/2026?",
    "2026-05-01から2026-05-31の会議件数を教えてください。": "Hãy cho biết số lượng cuộc họp từ ngày 01/05/2026 đến ngày 31/05/2026.",
    "参加者が最も多い会議はどれですか？": "Cuộc họp nào có nhiều người tham gia nhất?",
    "参加者数が一番少なかった会議は？": "Cuộc họp nào có ít người tham gia nhất?",
    "鈴木さんの発言回数は何回ですか？": "Số lần phát biểu của Suzuki là bao nhiêu?",
    "田中さんは今月何回発言しましたか？": "Tanaka đã phát biểu bao nhiêu lần trong tháng này?",
    "今月と先月の会議数の差はいくつですか？": "Sự khác biệt về số lượng cuộc họp giữa tháng này và tháng trước là bao nhiêu?",
    "今週の会議時間は先週と比べてどうですか？": "Thời gian họp tuần này so với tuần trước như thế nào?",
    "会議数が最も多い曜日はいつですか？": "Thứ mấy trong tuần có nhiều cuộc họp nhất?",
    "今月の会議数と合計時間を教えてください。": "Hãy cho biết số lượng cuộc họp và tổng thời gian họp trong tháng này.",
    "AiVoice Proの価格は月額いくらですか？": "Giá của AiVoice Pro là bao nhiêu một tháng?",
    "リファラルボーナスはいくらですか？": "Tiền thưởng giới thiệu là bao nhiêu?",
    "今月の会議件数をお教えいただけますでしょうか。": "Bạn có thể cho tôi biết số lượng cuộc họp trong tháng này không?",
    "先月の会議の総数をお知らせいただけますか。": "Bạn có thể thông báo tổng số cuộc họp tháng trước không?",
    "今月会議何件？": "Tháng này có bao nhiêu cuộc họp?",
    "会議数は？": "Số lượng cuộc họp là bao nhiêu?",
    "今月は会議がなかったのですか？": "Tháng này không có cuộc họp nào sao?",
    "先週は会議が一件もありませんでしたか？": "Tuần trước không có bất kỳ cuộc họp nào phải không?",
    "会議がどれくらいあったか知りたいです。": "Tôi muốn biết có bao nhiêu cuộc họp đã diễn ra.",
    "今月の会議数を確認したいのですが。": "Tôi muốn xác nhận số lượng cuộc họp trong tháng này.",
    "お忙しいところ恐縮ですが、今月中に開催された会議の総件数について確認させていただきたいのですが、教えていただけますでしょうか。": "Xin lỗi vì đã làm phiền, nhưng tôi muốn xác nhận tổng số cuộc họp diễn ra trong tháng này, bạn có thể cho tôi biết không?",
    "えーと、今月の会議は何件くらいありましたっけ？": "Ừm, tháng này có khoảng bao nhiêu cuộc họp nhỉ?",
    "音声認識システムのテスト消化率は何パーセントですか？": "Tỷ lệ hoàn thành kiểm thử hệ thống nhận dạng giọng nói là bao nhiêu phần trăm?",
    "ノイズキャンセリング問題の原因は何ですか？": "Nguyên nhân của vấn đề khử nhiễu là gì?",
    "第三四半期の予算申請の締め切りはいつですか？": "Hạn chót đăng ký ngân sách quý 3 là khi nào?",
    "エネルギー政策で提案された対策は何ですか？": "Các biện pháp đề xuất trong chính sách năng lượng là gì?",
    "AiVoice Proのローンチ日はいつですか？": "Ngày ra mắt AiVoice Pro là khi nào?",
    "新製品のターゲット市場はどこですか？": "Thị trường mục tiêu của sản phẩm mới là ở đâu?",
    "クローズドベータの参加企業数は何社ですか？": "Có bao nhiêu doanh nghiệp tham gia phiên bản thử nghiệm giới hạn (closed beta)?",
    "マーケティング予算の内訳を教えてください。": "Hãy cho tôi biết chi tiết ngân sách marketing.",
    "サーバー更新で電力消費をどれだけ削減できますか？": "Có thể giảm bao nhiêu mức tiêu thụ điện năng bằng cách nâng cấp máy chủ?",
    "採用計画で何名のエンジニアを募集していますか？": "Có bao nhiêu kỹ sư được tuyển dụng trong kế hoạch tuyển dụng?",
    "東京の天気は？": "Thời tiết ở Tokyo thế nào?",
    "ランチのおすすめを教えてください。": "Hãy giới thiệu cho tôi một vài gợi ý ăn trưa.",
    "会議": "Cuộc họp",
    "こんにちは": "Xin chào",
    "meetingは今月何件ありますか？": "Tháng này có bao nhiêu cuộc họp (meeting)?",
    "会議を削除してください。": "Hãy xóa cuộc họp.",
    "このシステムは何ができますか？": "Hệ thống này có thể làm được gì?",
    "3人で30分のミーティングをしたいのですが。": "Tôi muốn có một cuộc họp 30 phút cho 3 người.",
    "今月の会議が多すぎると思います。": "Tôi nghĩ tháng này có quá nhiều cuộc họp.",
    "今月の会議は何件ですか？それとも先月？": "Tháng này có bao nhiêu cuộc họp? Hay là tháng trước?",
    "昨日の会議の所要時間は何秒ですか？": "Thời lượng cuộc họp hôm qua là bao nhiêu giây?",
    "予算に関する会議はありましたか？": "Có cuộc họp nào liên quan đến ngân sách không?",
    "本日までの会議の累計件数をご教示ください。": "Hãy cho tôi biết tổng số lượng cuộc họp lũy kế cho đến hôm nay.",
    "今週の会議、全部で何時間？": "Tổng cộng tuần này có bao nhiêu giờ họp?",
    "来月の会議はまだ記録されていませんか？": "Cuộc họp tháng sau vẫn chưa được ghi lại phải không?",
    "Q1の売上目標達成率は何パーセントでしたか？": "Tỷ lệ hoàn thành mục tiêu doanh thu Q1 là bao nhiêu phần trăm?",
    "AiVoice Proの初年度売上目標は何億円ですか？": "Mục tiêu doanh thu năm đầu tiên của AiVoice Pro là bao nhiêu trăm triệu Yên?",
    "5月26日の会議で何が決まりましたか？": "Quyết định nào đã được đưa ra trong cuộc họp ngày 26 tháng 5?",
    "エネルギー政策についてどんな対応策が議論されましたか？": "Biện pháp ứng phó nào đối với chính sách năng lượng đã được thảo luận?",
    "田中さんは会議で何を指示しましたか？": "Tanaka đã chỉ thị những gì trong cuộc họp?",
    "ベータ版のリリース日はいつですか？": "Ngày phát hành bản beta là khi nào?",
    "会議のアクションアイテムを教えてください。": "Hãy cho biết các hành động cần thực hiện (action items) của cuộc họp.",
    "採用凍結の理由は何ですか？": "Lý do đóng băng tuyển dụng là gì?"
}

p_map = {
    "今月": "trong tháng này",
    "今週": "trong tuần này",
    "先月": "trong tháng trước",
    "今日": "hôm nay",
    "昨日": "hôm qua",
    "明日": "ngày mai",
    "来週": "trong tuần sau",
    "来月": "trong tháng sau",
    "今年の5月": "trong tháng 5 năm nay"
}

d_map = {
    "5月15日": "ngày 15 tháng 5",
    "5月20日": "ngày 20 tháng 5",
    "5月26日": "ngày 26 tháng 5",
    "2026年5月15日": "ngày 15 tháng 5 năm 2026",
    "2026年5月20日": "ngày 20 tháng 5 năm 2026",
    "2026年5月26日": "ngày 26 tháng 5 năm 2026",
    "2026-05-15": "15/05/2026",
    "2026-05-20": "20/05/2026",
    "2026-05-26": "26/05/2026"
}

topic_map = {
    "予算": "ngân sách",
    "音声認識": "nhận dạng giọng nói",
    "ノイズキャンセリング": "khử nhiễu",
    "エネルギー政策": "chính sách năng lượng",
    "太陽光パネル": "tấm pin mặt trời",
    "AiVoice Pro": "AiVoice Pro",
    "マーケティング": "marketing",
    "採用": "tuyển dụng",
    "ローンチ": "ra mắt",
    "クラウドコスト": "chi phí đám mây",
    "営業": "kinh doanh",
    "ベータ版": "bản beta"
}

speaker_map = {
    "田中": "Tanaka",
    "佐藤": "Sato",
    "鈴木": "Suzuki",
    "山田": "Yamada",
    "伊藤": "Ito",
    "中村": "Nakamura",
    "小林": "Kobayashi",
    "松本": "Matsumoto"
}

def local_translate(q: str) -> str:
    q_stripped = q.strip()
    if q_stripped in seeds:
        return seeds[q_stripped]
        
    result = q_stripped
    
    # 1. Topic replacements
    for jp, vi in topic_map.items():
        if jp in result:
            result = result.replace(jp, vi)
            
    # 2. Speaker replacements
    for jp, vi in speaker_map.items():
        if jp in result:
            result = result.replace(jp, vi)
            
    # 3. Period replacements
    for jp, vi in p_map.items():
        if jp in result:
            result = result.replace(jp, vi)
            
    # 4. Date replacements
    for jp, vi in d_map.items():
        if jp in result:
            result = result.replace(jp, vi)
            
    # Grammar maps
    grammar = {
        "の会議は何件ですか？": " có bao nhiêu cuộc họp?",
        "の会議件数を教えてください。": " hãy cho biết số lượng cuộc họp.",
        "は何回会議がありましたか？": " đã có bao nhiêu cuộc họp?",
        "には会議が何件ありますか？": " có bao nhiêu cuộc họp?",
        "の会議は記録されていますか？": " các cuộc họp có được ghi lại không?",
        "の会議数は？": " số lượng cuộc họp là bao nhiêu?",
        "、会議はありましたか？": ", có cuộc họp nào không?",
        "、何か会議がありましたか？": ", có cuộc họp nào diễn ra không?",
        "に会議はありましたか？": " có cuộc họp nào không?",
        "の会議時間の合計は何秒ですか？": " có tổng thời gian họp là bao nhiêu giây?",
        "の合計会議時間を教えてください。": " hãy cho biết tổng thời gian họp.",
        "の平均会議時間は何秒ですか？": " có thời gian họp trung bình là bao nhiêu giây?",
        "の会議時間は何秒ですか？": " thời gian họp là bao nhiêu giây?",
        "で最も長い会議の時間は？": " thời lượng cuộc họp dài nhất là bao nhiêu?",
        "で最短 of 会議時間は？": " thời lượng cuộc họp ngắn nhất là bao nhiêu?",
        "で最短の会議時間は？": " thời lượng cuộc họp ngắn nhất là bao nhiêu?",
        "で最もlongかった会議は？": " cuộc họp dài nhất là cuộc họp nào?",
        "で最も短い会議は？": " cuộc họp ngắn nhất là cuộc họp nào?",
        "の会議数を日ごとに集計してください。": " hãy thống kê số lượng cuộc họp theo từng ngày.",
        "の会議時間を日別に教えてください。": " hãy thống kê thời gian họp theo từng ngày.",
        "の会議数を話者ごとに教えてください。": " hãy thống kê số lượng cuộc họp theo từng người nói.",
        "の会議時間を話者別に集計してください。": " hãy thống kê tổng thời gian họp theo từng người nói.",
        "の会議件数をユーザーごとに集計してください。": " hãy thống kê số lượng cuộc họp theo từng người dùng.",
        "について話した会議は何件ですか？": " có bao nhiêu cuộc họp thảo luận về?",
        "に関する会議は": " có bao nhiêu cuộc họp liên quan đến ",
        "何件ありますか？": " không?",
        "の話が出た会議を": " hãy cho biết các cuộc họp nhắc đến ",
        "教えてください。": " không?",
        "の会議で": " trong cuộc họp ",
        "について話しましたか？": " có nói về không?",
        "は": " vào ",
        "の会議で予算について何分頃に発言しましたか？": " phát biểu về ngân sách vào khoảng phút thứ mấy?",
        "は何時頃に発言しましたか？": " phát biểu vào khoảng mấy giờ?",
        "が": " phát biểu vào giây thứ mấy của cuộc họp ",
        "に発言したのは何秒目ですか？": " ?",
        "の会議の要約を教えてください。": " hãy cho biết tóm tắt cuộc họp.",
        "について詳しく説明してください。": " hãy giải thích chi tiết về.",
        "で合意された内容は何ですか？": " nội dung được đồng thuận là gì?",
        "から": " đến ",
        "までの会議は何件ですか？": " có bao nhiêu cuộc họp?",
        "までの合計会議時間は？": " tổng thời gian họp là bao nhiêu?",
        "までの会議を日別に集計してください。": " hãy thống kê cuộc họp theo ngày."
    }
    
    for jp, vi in grammar.items():
        if jp in result:
            result = result.replace(jp, vi)
            
    # Basic cleanup
    result = result.replace("の", " của ")
    result = result.replace("件数は？", " số lượng cuộc họp là bao nhiêu?")
    result = result.replace("時間の合計は？", " tổng thời gian họp là bao nhiêu?")
    
    return result.strip()

async def main():
    sys.stdout.reconfigure(encoding='utf-8')
    md_path = Path("eval/evaluation_report_200_honest.md")
    if not md_path.exists():
        print(f"Error: {md_path} does not exist. Run evaluation first.")
        return
        
    print("Reading and parsing evaluation report...")
    content = md_path.read_text(encoding="utf-8")
    
    # Extract table rows
    lines = content.splitlines()
    table_lines = []
    
    for line in lines:
        if line.strip().startswith("|") and "Dòng" not in line and "---" not in line:
            table_lines.append(line.strip())
            
    print(f"Found {len(table_lines)} table rows in the report.")
    
    # Parse rows
    parsed_rows = []
    for line in table_lines:
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 7:
            row_num = parts[1]
            question = parts[2]
            actual_sql = parts[3].strip("`")
            query_result = parts[4]
            desired_sql = parts[5].strip("`")
            status = parts[6]
            
            parsed_rows.append({
                "row": int(row_num),
                "question_ja": question,
                "question_vi": local_translate(question),
                "actual_sql": actual_sql,
                "query_result": query_result,
                "desired_sql": desired_sql,
                "status": "PASS" if "Đúng" in status else "FAIL",
                "status_raw": status
            })

    # HTML template generation
    html_content = """<!DOCTYPE html>
<html lang="vi" class="h-full bg-slate-950 text-slate-100">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Numeric SQL Tool - Báo cáo Đánh giá 200 Test Cases</title>
    <!-- Tailwind CSS v3 -->
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    fontFamily: {
                        sans: ['Outfit', 'Inter', 'sans-serif'],
                    },
                    colors: {
                        brand: {
                            50: '#f0f9ff',
                            100: '#e0f2fe',
                            200: '#bae6fd',
                            500: '#0ea5e9',
                            600: '#0284c7',
                            700: '#0369a1',
                            950: '#03233e',
                        }
                    }
                }
            }
        }
    </script>
    <!-- Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        .glass {
            background: rgba(15, 23, 42, 0.65);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.05);
        }
        /* Custom Scrollbar */
        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        ::-webkit-scrollbar-track {
            background: #020617;
        }
        ::-webkit-scrollbar-thumb {
            background: #1e293b;
            border-radius: 4px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: #334155;
        }
    </style>
</head>
<body class="flex flex-col min-h-full font-sans antialiased selection:bg-brand-500 selection:text-white">

    <!-- Header / Navbar -->
    <header class="sticky top-0 z-40 w-full border-b border-slate-900 bg-slate-950/80 backdrop-blur-md">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <div class="flex items-center space-x-3">
                <div class="w-9 h-9 rounded-lg bg-gradient-to-tr from-brand-600 to-cyan-400 flex items-center justify-center font-bold text-white shadow-md shadow-brand-500/20">
                    N
                </div>
                <div>
                    <h1 class="text-md font-bold tracking-tight text-white">Numeric SQL Tool</h1>
                    <p class="text-xs text-slate-400">Dashboard Đối Soát & Đánh Giá</p>
                </div>
            </div>
            <div class="flex items-center space-x-4">
                <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    <span class="w-1.5 h-1.5 mr-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                    Database Live
                </span>
            </div>
        </div>
    </header>

    <!-- Main Content -->
    <main class="flex-grow max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        
        <!-- Welcome Hero Stats Card -->
        <div class="relative overflow-hidden rounded-2xl border border-slate-900 bg-gradient-to-b from-slate-900 to-slate-950 p-6 sm:p-8 shadow-2xl">
            <div class="absolute top-0 right-0 -mt-4 -mr-4 w-56 h-56 rounded-full bg-brand-500/10 blur-3xl"></div>
            <div class="absolute bottom-0 left-0 -mb-4 -ml-4 w-72 h-72 rounded-full bg-indigo-500/5 blur-3xl"></div>
            
            <div class="relative z-10 grid grid-cols-1 md:grid-cols-4 gap-6 items-center">
                <div class="md:col-span-2 space-y-2">
                    <h2 class="text-2xl sm:text-3xl font-extrabold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-white via-slate-100 to-slate-400">
                        Báo Cáo Đánh Giá Trung Thực
                    </h2>
                    <p class="text-sm text-slate-400 max-w-md">
                        Kết quả đối chiếu cú pháp SQL và thực thi số liệu trực tiếp trên cơ sở dữ liệu PostgreSQL cho bộ 200 câu hỏi tiếng Nhật nâng cao.
                    </p>
                    <div class="pt-2 text-xs text-slate-500 flex items-center space-x-2">
                        <span>Ngày đánh giá: """ + date.today().isoformat() + """</span>
                        <span>•</span>
                        <span>Chế độ: Regex Heuristics (Simple Mode)</span>
                    </div>
                </div>
                
                <div class="grid grid-cols-3 md:col-span-2 gap-4 text-center">
                    <div class="bg-slate-950/60 rounded-xl p-4 border border-slate-900">
                        <div class="text-3xl font-bold text-white" id="stat-total">0</div>
                        <div class="text-[10px] uppercase font-bold text-slate-400 tracking-wider mt-1">Tổng số case</div>
                    </div>
                    <div class="bg-slate-950/60 rounded-xl p-4 border border-slate-900">
                        <div class="text-3xl font-bold text-emerald-400" id="stat-pass">0</div>
                        <div class="text-[10px] uppercase font-bold text-slate-400 tracking-wider mt-1">Đạt (PASS)</div>
                    </div>
                    <div class="bg-emerald-950/20 rounded-xl p-4 border border-emerald-900/30 ring-1 ring-emerald-500/10">
                        <div class="text-3xl font-bold text-emerald-400" id="stat-accuracy">0%</div>
                        <div class="text-[10px] uppercase font-bold text-slate-400 tracking-wider mt-1">Độ chính xác</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Filters Section -->
        <div class="glass rounded-xl p-4 sm:p-6 shadow-md flex flex-col md:flex-row gap-4 items-center justify-between">
            <div class="relative w-full md:max-w-md">
                <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                    <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                </div>
                <input type="text" id="search-input" placeholder="Tìm kiếm câu hỏi (JP/VI) hoặc SQL..." 
                       class="w-full bg-slate-950 border border-slate-800 rounded-lg pl-10 pr-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500 transition-colors">
            </div>
            
            <div class="flex flex-wrap gap-2 w-full md:w-auto justify-end">
                <button onclick="setFilter('ALL')" id="filter-all" class="px-4 py-2 rounded-lg text-xs font-semibold bg-brand-600 text-white shadow-lg shadow-brand-500/10 hover:bg-brand-500 transition-colors">
                    Tất cả
                </button>
                <button onclick="setFilter('SQL')" id="filter-sql" class="px-4 py-2 rounded-lg text-xs font-semibold bg-slate-900 text-slate-300 hover:bg-slate-800 border border-slate-800 transition-colors">
                    Có chạy SQL
                </button>
                <button onclick="setFilter('SKIP')" id="filter-skip" class="px-4 py-2 rounded-lg text-xs font-semibold bg-slate-900 text-slate-300 hover:bg-slate-800 border border-slate-800 transition-colors">
                    Bị loại bỏ (SKIP)
                </button>
            </div>
        </div>

        <!-- Table View -->
        <div class="glass rounded-xl shadow-xl overflow-hidden border border-slate-900">
            <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="bg-slate-950/80 border-b border-slate-900 text-slate-400 text-xs uppercase font-bold tracking-wider">
                            <th class="py-4 px-6 text-center w-16">#</th>
                            <th class="py-4 px-6 md:w-96">Nội dung câu hỏi (JA & VI)</th>
                            <th class="py-4 px-6">Câu lệnh SQL thực tế sinh ra</th>
                            <th class="py-4 px-6 w-48 text-center">Kết quả truy vấn</th>
                            <th class="py-4 px-6 w-24 text-center">Kết quả</th>
                        </tr>
                    </thead>
                    <tbody id="testcases-list" class="divide-y divide-slate-900 text-sm">
                        <!-- Data rows injected by JS -->
                    </tbody>
                </table>
            </div>
            
            <!-- Empty State -->
            <div id="empty-state" class="hidden py-16 text-center space-y-3">
                <svg class="mx-auto h-12 w-12 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <h3 class="text-sm font-semibold text-slate-300">Không tìm thấy kết quả</h3>
                <p class="text-xs text-slate-500">Thử thay đổi từ khóa tìm kiếm hoặc bộ lọc của bạn.</p>
            </div>
        </div>

    </main>

    <!-- Footer -->
    <footer class="mt-auto border-t border-slate-900 bg-slate-950 py-6 text-center text-xs text-slate-500">
        <p>© 2026 Numeric SQL Tool. Giao diện thiết kế cao cấp cho đối soát dữ liệu.</p>
    </footer>

    <!-- JSON DATA EMBEDDED -->
    <script>
        const testcases = """ + json.dumps(parsed_rows, ensure_ascii=False) + """;
        
        let currentFilter = 'ALL';
        let searchQuery = '';

        // Dom elements
        const listEl = document.getElementById('testcases-list');
        const emptyStateEl = document.getElementById('empty-state');
        const searchInput = document.getElementById('search-input');
        
        // Stats
        document.getElementById('stat-total').innerText = testcases.length;
        const passedCases = testcases.filter(t => t.status === 'PASS').length;
        document.getElementById('stat-pass').innerText = passedCases;
        document.getElementById('stat-accuracy').innerText = `${((passedCases / testcases.length) * 100).toFixed(2)}%`;

        // Search listener
        searchInput.addEventListener('input', (e) => {
            searchQuery = e.target.value.toLowerCase().trim();
            renderTable();
        });

        function setFilter(filter) {
            currentFilter = filter;
            
            // Update filter buttons styling
            const buttons = {
                'ALL': document.getElementById('filter-all'),
                'SQL': document.getElementById('filter-sql'),
                'SKIP': document.getElementById('filter-skip')
            };
            
            Object.keys(buttons).forEach(key => {
                if (key === filter) {
                    buttons[key].className = "px-4 py-2 rounded-lg text-xs font-semibold bg-brand-600 text-white shadow-lg shadow-brand-500/10 hover:bg-brand-500 transition-colors";
                } else {
                    buttons[key].className = "px-4 py-2 rounded-lg text-xs font-semibold bg-slate-900 text-slate-300 hover:bg-slate-800 border border-slate-800 transition-colors";
                }
            });

            renderTable();
        }

        function copySQL(text, buttonId) {
            navigator.clipboard.writeText(text).then(() => {
                const btn = document.getElementById(buttonId);
                const originalText = btn.innerHTML;
                btn.innerHTML = `
                    <svg class="w-3 h-3 text-emerald-400 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" />
                    </svg> Copied!
                `;
                btn.classList.add('border-emerald-500/30', 'text-emerald-400');
                
                setTimeout(() => {
                    btn.innerHTML = originalText;
                    btn.classList.remove('border-emerald-500/30', 'text-emerald-400');
                }, 1500);
            });
        }

        function renderTable() {
            // Filter list
            const filtered = testcases.filter(item => {
                // Search filter
                const matchesSearch = 
                    item.question_ja.toLowerCase().includes(searchQuery) ||
                    item.question_vi.toLowerCase().includes(searchQuery) ||
                    item.actual_sql.toLowerCase().includes(searchQuery);

                // Type filter
                let matchesType = true;
                if (currentFilter === 'SQL') {
                    matchesType = !item.actual_sql.startsWith('SKIP');
                } else if (currentFilter === 'SKIP') {
                    matchesType = item.actual_sql.startsWith('SKIP');
                }

                return matchesSearch && matchesType;
            });

            // Handle empty state
            if (filtered.length === 0) {
                listEl.innerHTML = '';
                emptyStateEl.classList.remove('hidden');
                return;
            }
            emptyStateEl.classList.add('hidden');

            // Render rows
            listEl.innerHTML = filtered.map((item, index) => {
                const isSkip = item.actual_sql.startsWith('SKIP');
                
                // Format SQL layout
                let sqlLayout = '';
                if (isSkip) {
                    sqlLayout = `
                        <div class="px-3 py-1.5 rounded-lg bg-slate-950 text-slate-500 font-mono text-xs border border-slate-900 select-all break-words">
                            ${item.actual_sql}
                        </div>
                    `;
                } else {
                    const btnId = `copy-btn-${item.row}`;
                    sqlLayout = `
                        <div class="group/sql relative">
                            <pre class="p-3 rounded-lg bg-slate-950 text-slate-300 font-mono text-xs border border-slate-900 overflow-x-auto whitespace-pre-wrap select-all max-h-48 break-words">${item.actual_sql}</pre>
                            <button id="${btnId}" onclick="copySQL('${item.actual_sql.replace(/'/g, "\\'")}', '${btnId}')" 
                                    class="absolute top-2 right-2 opacity-0 group-hover/sql:opacity-100 flex items-center px-2 py-1 bg-slate-900 border border-slate-800 rounded text-[10px] font-semibold text-slate-400 hover:bg-slate-800 hover:text-white transition-all shadow-md">
                                <svg class="w-3 h-3 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                                </svg> Copy SQL
                            </button>
                        </div>
                    `;
                }

                // Format query result layout
                let queryResultLayout = '';
                if (isSkip) {
                    queryResultLayout = `<span class="text-slate-600 font-mono">-</span>`;
                } else {
                    queryResultLayout = `
                        <span class="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-semibold bg-brand-500/10 text-brand-400 border border-brand-500/10 font-mono">
                            ${item.query_result}
                        </span>
                    `;
                }

                // Format status layout
                const statusLayout = `
                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        Đúng
                    </span>
                `;

                return `
                    <tr class="hover:bg-slate-900/40 transition-colors">
                        <td class="py-4 px-6 text-center font-mono text-xs text-slate-500">${item.row}</td>
                        <td class="py-4 px-6 space-y-1.5">
                            <p class="font-medium text-slate-100 text-sm leading-relaxed">${item.question_ja}</p>
                            <p class="text-xs text-slate-400 italic font-normal leading-relaxed">${item.question_vi}</p>
                        </td>
                        <td class="py-4 px-6">${sqlLayout}</td>
                        <td class="py-4 px-6 text-center">${queryResultLayout}</td>
                        <td class="py-4 px-6 text-center">${statusLayout}</td>
                    </tr>
                `;
            }).join('');
        }

        // Init
        renderTable();
    </script>
</body>
</html>
"""
    
    out_html_path = Path("eval/evaluation_dashboard.html")
    out_html_path.write_text(html_content, encoding="utf-8")
    print(f"HTML Dashboard successfully created at: {out_html_path}")

if __name__ == "__main__":
    asyncio.run(main())
