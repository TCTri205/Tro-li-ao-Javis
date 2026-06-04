import random
import pandas as pd
from pathlib import Path
import sys

# Setup seed for reproducibility
random.seed(12345)

ROOT = Path(__file__).resolve().parents[1]

# Predefined SQL templates
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

# Pools of data docs components
speakers = ['田中', '鈴木', '佐藤', '山田', '伊藤', '中村', '小林', '松本']

topics = [
    ('音声認識システム', '進捗状況'),
    ('ノイズキャンセリング', 'タイミング問題'),
    ('クラウドコスト', '予算超過'),
    ('採用凍結', '事業計画への影響'),
    ('太陽光パネル', '初期費用と補助金'),
    ('サーバー更新', '電力消費の削減'),
    ('研修プログラム', '省エネ意識の向上'),
    ('営業レビュー', '売上目標の達成率'),
    ('マーケティング戦略', 'SNS広告の予算'),
    ('展示会', 'デモブースの設置'),
    ('AiVoice Pro', '処理速度と認識精度'),
    ('ニューラルネットワーク', '日本語特化の調整'),
    ('セキュリティ基盤', 'ISO27001の認定'),
    ('価格戦略', 'プロフェッショナルプラン')
]

single_days = [
    '5月15日', '5月20日', '5月26日',
    '2026年5月15日', '2026年5月20日', '2026年5月26日',
    '今日', '本日', '昨日', '明日'
]

multi_days = [
    '今月', '先月', '今週', '先週',
    '5月15日から5月20日', '5月15日から5月26日', '5月20日から5月26日',
    '2026年5月15日から2026年5月26日', '2026年5月20日から2026年5月26日'
]

all_periods = single_days + multi_days

def generate_pools():
    valid_pool = []
    
    # 1. COUNT
    count_tpls = [
        "{period}に会議は何回開催されましたか？",
        "{period}の会議件数は何件でしたか？",
        "{period}の期間に会議は何回ありましたか？",
        "{period}の会議は何回カウントされますか？",
        "{period}に開催された会議数を教えてください。"
    ]
    for period in all_periods:
        for tpl in count_tpls:
            valid_pool.append((tpl.format(period=period), SQL_COUNT))
            
    # 2. SUM
    sum_tpls = [
        "{period}の合計会議時間は何秒ですか？",
        "{period}の所要時間は何秒ですか？",
        "{period}の会議の合計時間は何秒になりますか？",
        "{period}の総会議時間は何秒ですか？",
        "{period}の会議の長さの合計は何秒ですか？"
    ]
    for period in all_periods:
        for tpl in sum_tpls:
            valid_pool.append((tpl.format(period=period), SQL_SUM))

    # 3. AVG
    avg_tpls = [
        "{period}の平均会議時間は何秒ですか？",
        "{period}に行われた会議の平均時間は？",
        "{period}の会議の平均所要時間は何秒ですか？",
        "{period}の平均時間は何秒ですか？"
    ]
    for period in all_periods:
        for tpl in avg_tpls:
            valid_pool.append((tpl.format(period=period), SQL_AVG))

    # 4. MAX
    max_tpls = [
        "{period}で最も長い会議時間は何秒ですか？",
        "{period}で一番長い所要時間は？",
        "{period}で最長の所要時間は何秒ですか？",
        "{period}の最大会議時間は何秒ですか？"
    ]
    for period in all_periods:
        for tpl in max_tpls:
            valid_pool.append((tpl.format(period=period), SQL_MAX))

    # 5. MIN
    min_tpls = [
        "{period}で最も短い会議時間は何秒ですか？",
        "{period}で一番短い会議時間は？",
        "{period}で最短の会議時間は何秒ですか？",
        "{period}の最小会議時間は何秒ですか？"
    ]
    for period in all_periods:
        for tpl in min_tpls:
            valid_pool.append((tpl.format(period=period), SQL_MIN))

    # 6. GROUP_SPEAKER
    speaker_tpls = [
        "{period}の会議数を話者ごとに教えてください。",
        "{period}の話者別の会議件数は何件ですか？",
        "話者別の会議件数は何件ですか？{period}で集計してください。",
        "{period}の会議数を話者別で教えてください。"
    ]
    for period in all_periods:
        for tpl in speaker_tpls:
            valid_pool.append((tpl.format(period=period), SQL_GROUP_SPEAKER))

    # 7. GROUP_DAY_COUNT
    day_count_tpls = [
        "{period}の会議件数の日別の集計を教えてください。",
        "{period}の会議を日ごとに集計してください。",
        "{period}の会議件数を日別で教えてください。",
        "{period}の会議数を日別で集計してください。"
    ]
    for period in multi_days:
        for tpl in day_count_tpls:
            valid_pool.append((tpl.format(period=period), SQL_GROUP_DAY_COUNT))

    # 8. GROUP_DAY_SUM
    day_sum_tpls = [
        "{period}の会議時間を日別に集計してください。",
        "{period}の合計時間を日別で教えてください。",
        "{period}の所要時間を日別に集計してください。",
        "{period}の日ごとの合計会議時間を教えてください。"
    ]
    for period in multi_days:
        for tpl in day_sum_tpls:
            valid_pool.append((tpl.format(period=period), SQL_GROUP_DAY_SUM))

    skip_pool = []
    
    # 1. Semantic/Qualitative questions
    qual_tpls = [
        "{period}の会議で{speaker}さんが発言した{topic}の進捗について詳細を教えてください。",
        "{speaker}さんが説明した{topic}に関する{detail}の内容は何ですか？",
        "{period}の会議で{speaker}さんが言及した{topic}の課題は何ですか？",
        "{topic}の{detail}が決定した理由について分析したレポートを共有してください。",
        "{speaker}さんと{speaker2}さん、どちらが{topic}について詳しく説明しましたか？",
        "{period}の会議の議題として何がアジェンダに入っていましたか？",
        "{topic}の{detail}に関する実施計画書をまとめて提案してください。",
        "{speaker}さんが会議の最後に行った挨拶のテーマは何でしたか？",
        "{period}の会議で{speaker}さんが懸念を示した具体的な問題は何ですか？",
        "{topic}の導入により期待されるコスト削減効果の根拠は何ですか？",
        "{speaker}さんが提出した{topic}のフォローアップについて教えてください。",
        "{topic}のリリース予定日はいつですか？",
        "{topic}の件について、どのような対応策が合意されましたか？"
    ]
    
    for period in all_periods:
        for tpl in qual_tpls:
            sp = random.choice(speakers)
            sp2 = random.choice([s for s in speakers if s != sp])
            topic, detail = random.choice(topics)
            skip_pool.append((tpl.format(period=period, speaker=sp, speaker2=sp2, topic=topic, detail=detail), SQL_SKIP))

    # 2. Unsupported operations
    unsupported_tpls = [
        "{period}の全会議における{topic}関連の割合は何パーセントですか？",
        "{period}の会議時間の中央値はどれくらいですか？",
        "{period}の会議数の週ごとの推移を教えてください。",
        "{period}の平日のみの合計所要時間は何秒ですか？",
        "{period}で2番目に長かった会議の時間は？",
        "{period}の上旬に開催された会議の件数は？",
        "{period}のQ1の売上目標達成率は？",
        "{period}の第3週のスケジュールはどうなっていますか？"
    ]
    for period in all_periods:
        for tpl in unsupported_tpls:
            topic, _ = random.choice(topics)
            skip_pool.append((tpl.format(period=period, topic=topic), SQL_SKIP))

    # 3. Cross-user queries
    cross_user_tpls = [
        "ユーザーごとの{period}の会議件数は何件ですか？",
        "ユーザー別で{period}の合計会議時間を集計してください。",
        "{period}の会議時間をユーザー別で教えてください。"
    ]
    for period in all_periods:
        for tpl in cross_user_tpls:
            skip_pool.append((tpl.format(period=period), SQL_SKIP))

    # 4. Multiple metrics queries
    multi_metrics_tpls = [
        "{period}の会議は何回あり、その合計時間は何秒でしたか？",
        "{period}の会議件数と平均会議時間を教えてください。"
    ]
    for period in all_periods:
        for tpl in multi_metrics_tpls:
            skip_pool.append((tpl.format(period=period), SQL_SKIP))
            
    return valid_pool, skip_pool

def main():
    # Load existing questions to prevent duplicates
    existing_questions = set()
    csv_path = ROOT / 'eval' / 'random_100_testcases_ja.csv'
    if csv_path.exists():
        try:
            df_old = pd.read_csv(csv_path)
            existing_questions = set(df_old['question'].tolist())
            print(f"Loaded {len(existing_questions)} existing questions to avoid duplication.")
        except Exception as e:
            print(f"Could not load existing CSV: {e}")
            
    valid_pool, skip_pool = generate_pools()
    
    # Shuffle pools
    random.shuffle(valid_pool)
    random.shuffle(skip_pool)
    
    final_valid = []
    final_skip = []
    
    # Filter valid
    for q, sql in valid_pool:
        if q not in existing_questions and q not in [x[0] for x in final_valid]:
            final_valid.append((q, sql))
        if len(final_valid) == 50:
            break
            
    # Filter skip
    for q, sql in skip_pool:
        if q not in existing_questions and q not in [x[0] for x in final_skip]:
            final_skip.append((q, sql))
        if len(final_skip) == 50:
            break
            
    print(f"Generated {len(final_valid)} unique Valid cases and {len(final_skip)} unique Skip cases.")
    
    if len(final_valid) < 50 or len(final_skip) < 50:
        print("Error: Could not generate enough unique test cases. Try expanding the templates or pools.")
        sys.exit(1)
        
    # Combine and shuffle
    testcases = final_valid + final_skip
    random.shuffle(testcases)
    
    # Export to CSV
    df = pd.DataFrame(testcases, columns=['question', 'sql'])
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False, encoding='utf-8')
    print(f"Successfully exported new random 100 test cases to {csv_path}")
    
    # Export to questions list txt
    txt_path = ROOT / 'db' / 'questions_random_100_ja.txt'
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    with open(txt_path, 'w', encoding='utf-8') as f:
        for q, _ in testcases:
            f.write(q + '\n')
    print(f"Successfully exported new questions list to {txt_path}")

if __name__ == '__main__':
    main()
