import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Ground Truth SQL statements matching the templates
SQL_COUNT = (
    "SELECT COUNT(DISTINCT t.id) AS value FROM transcripts t WHERE "
    "($1::uuid IS NULL OR t.user_id = $1::uuid) AND "
    "($2::date IS NULL OR t.meeting_date >= $2::date) AND "
    "($3::date IS NULL OR t.meeting_date <= $3::date) AND "
    "($4::text IS NULL OR t.summary ILIKE '%' || $4 || '%' OR t.raw_text ILIKE '%' || $4 || '%')"
)

SQL_SUM = (
    "SELECT COALESCE(SUM(t.duration_seconds), 0) AS value FROM transcripts t WHERE "
    "($1::uuid IS NULL OR t.user_id = $1::uuid) AND "
    "($2::date IS NULL OR t.meeting_date >= $2::date) AND "
    "($3::date IS NULL OR t.meeting_date <= $3::date) AND "
    "($4::text IS NULL OR t.summary ILIKE '%' || $4 || '%' OR t.raw_text ILIKE '%' || $4 || '%')"
)

SQL_AVG = (
    "SELECT COALESCE(AVG(t.duration_seconds), 0) AS value FROM transcripts t WHERE "
    "($1::uuid IS NULL OR t.user_id = $1::uuid) AND "
    "($2::date IS NULL OR t.meeting_date >= $2::date) AND "
    "($3::date IS NULL OR t.meeting_date <= $3::date) AND "
    "($4::text IS NULL OR t.summary ILIKE '%' || $4 || '%' OR t.raw_text ILIKE '%' || $4 || '%')"
)

SQL_MAX = (
    "SELECT t.id::text AS transcript_id, t.session_id AS session_id, "
    "t.meeting_date::text AS meeting_date, t.participants AS participants, "
    "t.duration_seconds AS value, t.summary AS summary FROM transcripts t WHERE "
    "($1::uuid IS NULL OR t.user_id = $1::uuid) AND "
    "($2::date IS NULL OR t.meeting_date >= $2::date) AND "
    "($3::date IS NULL OR t.meeting_date <= $3::date) AND "
    "($4::text IS NULL OR t.summary ILIKE '%' || $4 || '%' OR t.raw_text ILIKE '%' || $4 || '%') "
    "AND t.duration_seconds IS NOT NULL ORDER BY t.duration_seconds DESC, t.meeting_date DESC LIMIT 1"
)

SQL_MIN = (
    "SELECT t.id::text AS transcript_id, t.session_id AS session_id, "
    "t.meeting_date::text AS meeting_date, t.participants AS participants, "
    "t.duration_seconds AS value, t.summary AS summary FROM transcripts t WHERE "
    "($1::uuid IS NULL OR t.user_id = $1::uuid) AND "
    "($2::date IS NULL OR t.meeting_date >= $2::date) AND "
    "($3::date IS NULL OR t.meeting_date <= $3::date) AND "
    "($4::text IS NULL OR t.summary ILIKE '%' || $4 || '%' OR t.raw_text ILIKE '%' || $4 || '%') "
    "AND t.duration_seconds IS NOT NULL ORDER BY t.duration_seconds ASC, t.meeting_date ASC LIMIT 1"
)

SQL_GROUP_SPEAKER = (
    "SELECT x.speaker AS group_key, COUNT(DISTINCT t.id) AS value FROM transcripts t "
    "JOIN (SELECT DISTINCT transcript_id, speaker FROM chunks_turn) x ON x.transcript_id = t.id WHERE "
    "($1::uuid IS NULL OR t.user_id = $1::uuid) AND "
    "($2::date IS NULL OR t.meeting_date >= $2::date) AND "
    "($3::date IS NULL OR t.meeting_date <= $3::date) AND "
    "($4::text IS NULL OR t.summary ILIKE '%' || $4 || '%' OR t.raw_text ILIKE '%' || $4 || '%') "
    "GROUP BY x.speaker ORDER BY value DESC LIMIT 20"
)

SQL_GROUP_DAY_COUNT = (
    "SELECT t.meeting_date::text AS group_key, COUNT(DISTINCT t.id) AS value FROM transcripts t WHERE "
    "($1::uuid IS NULL OR t.user_id = $1::uuid) AND "
    "($2::date IS NULL OR t.meeting_date >= $2::date) AND "
    "($3::date IS NULL OR t.meeting_date <= $3::date) AND "
    "($4::text IS NULL OR t.summary ILIKE '%' || $4 || '%' OR t.raw_text ILIKE '%' || $4 || '%') "
    "GROUP BY t.meeting_date ORDER BY group_key LIMIT 31"
)

SQL_GROUP_DAY_SUM = (
    "SELECT t.meeting_date::text AS group_key, COALESCE(SUM(t.duration_seconds), 0) AS value FROM transcripts t WHERE "
    "($1::uuid IS NULL OR t.user_id = $1::uuid) AND "
    "($2::date IS NULL OR t.meeting_date >= $2::date) AND "
    "($3::date IS NULL OR t.meeting_date <= $3::date) AND "
    "($4::text IS NULL OR t.summary ILIKE '%' || $4 || '%' OR t.raw_text ILIKE '%' || $4 || '%') "
    "GROUP BY t.meeting_date ORDER BY group_key LIMIT 31"
)

SQL_SKIP = "SKIP (operator=skip, target=none)"

# 100 Japanese test cases from data_docs
testcases = [
    # 50 Valid SQL Questions
    ("今月は会議が何回ありましたか？", SQL_COUNT),
    ("5月の会議件数は？", SQL_COUNT),
    ("5月26日の所要時間は何秒ですか？", SQL_SUM),
    ("2026年5月20日の会議時間は？", SQL_SUM),
    ("5月15日の合計会議時間は何秒？", SQL_SUM),
    ("5月の平均会議時間は？", SQL_AVG),
    ("今月の平均会議時間は何秒ですか？", SQL_AVG),
    ("5月で最も長い会議時間は何秒ですか？", SQL_MAX),
    ("5月で一番長い所要時間は？", SQL_MAX),
    ("5月で最も短い会議時間は何秒ですか？", SQL_MIN),
    ("5月で一番短い会議時間は？", SQL_MIN),
    ("5月の会議時間を日別に集計してください。", SQL_GROUP_DAY_SUM),
    ("5月の会議件数の日別の集計を教えてください。", SQL_GROUP_DAY_COUNT),
    ("今月の会議数を話者ごとに教えてください。", SQL_GROUP_SPEAKER),
    ("ユーザーごとの今月の会議件数は何件ですか？", SQL_SKIP), # cross-user defaults to SKIP
    ("昨日、会議は何件ありましたか？", SQL_COUNT),
    ("今日、会議は何件記録されていますか？", SQL_COUNT),
    ("本日開催された会議의合計時間は何秒ですか？", SQL_SUM),
    ("昨日行われた会議の平均時間は何秒ですか？", SQL_AVG),
    ("5月26日の会議は何回カウントされますか？", SQL_COUNT),
    ("5月20日に会議はありましたか？", SQL_COUNT),
    ("5月15日に何か会議は開催されましたか？", SQL_COUNT),
    ("今月の会議の合計時間は何秒ですか？", SQL_SUM),
    ("5月26日の会議の合計時間は何秒ですか？", SQL_SUM),
    ("5月20日の所要時間は何秒ですか？", SQL_SUM),
    ("5月15日の会議の長さは何秒ですか？", SQL_SUM),
    ("今週の会議の合計時間を教えてください。", SQL_SUM),
    ("先週의会議件数は何件でしたか？", SQL_COUNT),
    ("今週は何回の会議がありましたか？", SQL_COUNT),
    ("先週の合計会議時間は何秒ですか？", SQL_SUM),
    ("5月に開催された会議の総時間は何秒ですか？", SQL_SUM),
    ("5月の会議件数を教えてください。", SQL_COUNT),
    ("5月に会議は何回ありましたか？", SQL_COUNT),
    ("5月20日の会議は何秒ですか？", SQL_SUM),
    ("5月15日の会議時間は？", SQL_SUM),
    ("5月26日の合計時間は？", SQL_SUM),
    ("今月の会議件数を日別で教えてください。", SQL_GROUP_DAY_COUNT),
    ("5月の会議を日ごとに集計してください。", SQL_GROUP_DAY_COUNT), # Counting meetings by day is correct here
    ("話者別の会議件数は何件ですか？今月で集計してください。", SQL_GROUP_SPEAKER),
    ("ユーザー別での会議件数の集計結果は？", SQL_SKIP), # cross-user defaults to SKIP
    ("5月に記録された会議の平均時間は何秒ですか？", SQL_AVG),
    ("今月行われた全ての会議の平均時間を教えてください。", SQL_AVG),
    ("5月で最長の所要時間は何秒ですか？", SQL_MAX),
    ("5月で最短の会議時間は何秒ですか？", SQL_MIN),
    ("5月15日から5月26日までの会議件数は何件ですか？", SQL_COUNT),
    ("5月20日から5月26日までの合計時間は何秒ですか？", SQL_SUM),
    ("5月15日から5月20日までの平均時間は何秒ですか？", SQL_AVG),
    ("2026年5月15日から2026年5月26日までの会議数は？", SQL_COUNT),
    ("今月の最大会議時間は何秒ですか？", SQL_MAX),
    ("今月の最小会議時間は何秒ですか？", SQL_MIN),

    # 50 Skip Questions (Semantic, unsupported operations, temporal edge cases)
    ("5月26日の定例会議で田中さんが発表した今日のアジェンダは何ですか？", SQL_SKIP),
    ("営業部門の第一四半期の売上目標達成率は何パーセントでしたか？", SQL_SKIP),
    ("鈴木さんが開発している音声認識システムバージョン2.3の現在の進捗は？", SQL_SKIP),
    ("ノイズキャンセリング機能で見つかった問題の原因は何ですか？", SQL_SKIP),
    ("マルチスレッド処理のタイミング問題はいつ修正される見込みですか？", SQL_SKIP),
    ("クラウドサービスの利用量が予算の120%に達した理由は何ですか？", SQL_SKIP),
    ("クラウドリソース of 最適化により、毎月いくらの削減が見込めますか？", SQL_SKIP),
    ("来月からの採用凍結によって見込まれる月額の削減効果はいくらですか？", SQL_SKIP),
    ("採用凍結の決定が事業計画に与える影響は最小限と説明された根拠は何ですか？", SQL_SKIP),
    ("佐藤さんが来月28日の会議に向けて準備することになっているレポートは何ですか？", SQL_SKIP),
    ("5月20日の会議で鈴木さんが言及したインフラコストの最適化案は？", SQL_SKIP),
    ("5月15日の新エネルギー政策に関する会議で合意された対応方針は？", SQL_SKIP),
    ("エネルギー政策の担当役員として出席していたメンバーの名前は誰ですか？", SQL_SKIP),
    ("音声認識テストの進捗で、現在消化率が約70%と報告された機能は何ですか？", SQL_SKIP),
    ("A社との契約締結が遅れたことが原因で伸び悩んだ部門はどこですか？", SQL_SKIP),
    ("5月の全会議のうち、第一四半期予算について詳しく説明した会議はどれですか？", SQL_SKIP),
    ("田中さんと鈴木さん、どちらがこの会議で多くの発言をしましたか？", SQL_SKIP),
    ("5月の会議の中で、インフラコストの増加に反対する意見は誰から出ましたか？", SQL_SKIP),
    ("テスト環境での音声処理量が想定より多かったために発生した問題の対策は？", SQL_SKIP),
    ("現在最終面接まで進んでおり予定通り採用されることになったのは何名ですか？", SQL_SKIP),
    ("5月26日の予算に関する議論で、合計時間の何パーセントが最適化に費やされましたか？", SQL_SKIP),
    ("5月の会議時間の平均 và 中央値を比較するとどちらが大きいですか？", SQL_SKIP),
    ("ASR v2.3のベータ版リリース予定日は来月の何日と鈴木さんが発言しましたか？", SQL_SKIP),
    ("エネルギー対策として太陽光パネルの導入が却下された理由を分析してください。", SQL_SKIP),
    ("クラウド利用料が月額約120万円超過していることに対する田中さんの懸念は何ですか？", SQL_SKIP),
    ("鈴木さんはタイミング問題を何週間以内に解決できると保証しましたか？", SQL_SKIP),
    ("5月の第3週に行われた進捗レビューの主な決定事項は何でしたか？", SQL_SKIP),
    ("先月と比較して、クラウドコストの増加トレンドに変化はありましたか？", SQL_SKIP),
    ("山田さんが会議の後半で指摘したクラウド採用凍結のリスクは何ですか？", SQL_SKIP),
    ("5月の会議数のうち、予算に関する会議の割合は何％を占めていますか？", SQL_SKIP),
    ("今月の最初の2週間に開催された予算関連の打ち合わせを要約してください。", SQL_SKIP),
    ("5月の会議の間隔は平均して何日おきでしたか？", SQL_SKIP),
    ("5月15日の会議の後、鈴木さんがフォローアップとして提出した資料は？", SQL_SKIP),
    ("エネルギー政策への対応について、佐藤さんが最初に提案したアプローチは？", SQL_SKIP),
    ("クラウド費用の削減目標である月額80万円は達成可能であると判断された理由は？", SQL_SKIP),
    ("鈴木さんが5月26日の会議で最後に発言した締めくくりの言葉は何ですか？", SQL_SKIP),
    ("5月の勤務日（平日のみ）の合計会議時間は何秒ですか？", SQL_SKIP),
    ("今年のQ2における開発部門の追加費用は合計で何億円ですか？", SQL_SKIP),
    ("5月の会議で、2番目に長かった会議の議題は何でしたか？", SQL_SKIP),
    ("佐藤さんと山田さんが両方参加した会議で、決まったネクストアクションは？", SQL_SKIP),
    ("ASR開発ロードマップに関して、承認されなかった計画があればその理由を教えてください。", SQL_SKIP),
    ("5月15日のアジェンダ作成を担当した司会者は誰と説明されていますか？", SQL_SKIP),
    ("音声処理テストデータのうち、ベータ版の基準に達しなかった割合は？", SQL_SKIP),
    ("来月十五日にリリース予定の音声認識システムに関する懸念点として挙げられたものは？", SQL_SKIP),
    ("5月中旬に行われた予算に関する緊急会議の要約をお願いします。", SQL_SKIP),
    ("先月末（最終5営業日）に議論された新エネルギー政策の詳細は何ですか？", SQL_SKIP),
    ("5月の月曜日だけに開催された進捗確認ミーティングの件数は何件ですか？", SQL_SKIP),
    ("予算超過額が合計360万円に達した場合 của 具体的な改善提案を説明してください。", SQL_SKIP),
    ("5月20日 và 5月26日の会議、どちらがより生産的でしたか？", SQL_SKIP),
    ("今年に入ってから今日までの開発テストの合計時間を集計してください。", SQL_SKIP),
]

# Export to CSV
df = pd.DataFrame(testcases, columns=['question', 'sql'])
csv_path = ROOT / 'eval' / 'random_100_testcases_ja.csv'
csv_path.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(csv_path, index=False, encoding='utf-8')
print(f"Exported ground truth to {csv_path}")

# Export questions list txt
txt_path = ROOT / 'db' / 'questions_random_100_ja.txt'
txt_path.parent.mkdir(parents=True, exist_ok=True)
with open(txt_path, 'w', encoding='utf-8') as f:
    for q, _ in testcases:
        f.write(q + '\n')
print(f"Exported questions list to {txt_path}")
