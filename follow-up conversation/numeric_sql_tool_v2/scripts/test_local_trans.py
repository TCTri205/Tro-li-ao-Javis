import sys
import pandas as pd
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

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
    "5月15日の会議의所要時間は何秒ですか？": "Thời lượng cuộc họp ngày 15 tháng 5 là bao nhiêu giây?",
    "5月15日の会議の所要時間は何秒ですか？": "Thời lượng cuộc họp ngày 15 tháng 5 là bao nhiêu giây?",
    "5月20日の営業レビュー会議は何件カウントされますか？": "Có bao nhiêu cuộc họp đánh giá kinh doanh ngày 20 tháng 5 được tính?",
    "予算の話があった会議は何件ありますか？": "Có bao nhiêu cuộc họp nói về vấn đề ngân sách?",
    "AiVoice Proのローンチについて話した会議を教えてください。": "Hãy cho tôi biết những cuộc họp nói về việc ra mắt AiVoice Pro.",
    "話者ごとに、今月の会議数を集計してください。": "Hãy thống kê số lượng cuộc họp trong tháng này theo từng người nói.",
    "日ごとの会議件数を教えてください。今月でお願いします。": "Hãy cho biết số lượng cuộc họp theo từng ngày trong tháng này.",
    "今週の合計会議時間は何秒ですか？": "Tổng thời gian họp tuần này là bao nhiêu giây?",
    "先月の平均会議時間を教えてください。": "Hãy cho biết thời gian họp trung bình tháng trước.",
    "一番短かった会議はどの日ですか？": "Cuộc họp ngắn nhất là vào ngày nào?",
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
    "話者側の会議件数はどうなっていますか？": "Số lượng cuộc họp theo từng người nói là bao nhiêu?",
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
    "お忙しいところ恐縮ですが、今月中に開催された会議 của 総件数について確認させていただきたいのですが、教えていただけますでしょうか。": "Xin lỗi vì đã làm phiền, nhưng tôi muốn xác nhận tổng số cuộc họp diễn ra trong tháng này, bạn có thể cho tôi biết không?",
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
    "来月の会議はまだ記録されていませんか？": "Cuộc họp tháng sau vẫn chưa được ghi lại phải không?"
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

df = pd.read_csv('eval/combined_200_testcases_ja.csv')
questions = list(df['question'])
unmapped = []
for q in questions:
    vi = local_translate(q)
    if vi == q or any(char in vi for char in ['の', '日', '月', '会', '議', '何', '件', '教', '数', '話', '集', '計', '時']):
        # If it contains Japanese characters or hasn't changed
        unmapped.append(q)

print('Unmapped questions:', len(unmapped))
if unmapped:
    print('First 10 unmapped:')
    for u in unmapped[:10]:
        print('  ', u)
