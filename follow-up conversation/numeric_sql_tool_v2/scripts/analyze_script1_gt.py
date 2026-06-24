import re
from collections import Counter

transcript = """[00:00:00-00:00:02][SPEAKER 1] お電話かわります。トウノです。
[00:00:02-00:00:04][SPEAKER 2] あ、すいません、シカズです。
[00:00:05-00:00:08][SPEAKER 1] あ、えーと、梅田さんの場合、10月19日に。
[00:00:08-00:00:08][SPEAKER 2] はい。
[00:00:08-00:00:11][SPEAKER 1] 返信から送りさせておいておりますして。
[00:00:11-00:00:11][SPEAKER 2] はい。
[00:00:12-00:00:15][SPEAKER 1] お手元には届いていないという状態でしょうか？
[00:00:16-00:00:21][SPEAKER 2] あ、いや、今工事終わりで、ちょっとごめんなさい。現場から、配信終わりですか、なしですか、確認入ってたんで、すみません。
[00:00:24-00:00:26][SPEAKER 1] あ、はい。実際あり、行ったと思います。
[00:00:26-00:00:30][SPEAKER 2] あ、了解いたしました。スリーラスターさんもですかね。
[00:00:30-00:00:31][SPEAKER 1] もう一度お願いします。
[00:00:32-00:00:35][SPEAKER 2] あ、スリーラスターさんも一緒ですよね、そしたら。
[00:00:35-00:00:37][SPEAKER 1] スリー、スリー。
[00:00:37-00:00:38][SPEAKER 2] ラスター。
[00:00:39-00:00:40][SPEAKER 1] 外人のことですか？
[00:00:41-00:00:42][SPEAKER 2] 会社名ですかね、これ。
[00:00:43-00:00:44][SPEAKER 1] あー、少々お待ちくださいね。
[00:00:45-00:00:47][SPEAKER 1] スリーラスター様は、購入なんで、サイズ書なしです。
[00:00:49-00:00:51][SPEAKER 2] 確か、梅田さんだけありですね。
[00:01:29-00:01:33][SPEAKER 1] 梅田様はありです。はい。
[00:01:33-00:01:33][SPEAKER 2] はい、わかりました。ありがとうございます。
[00:01:34-00:01:35][SPEAKER 1] お願いいたします。
[00:01:36-00:01:37][SPEAKER 2] あー、はい。
[00:01:37-00:01:40][SPEAKER 1] 失礼いたしました。
[00:01:39-00:01:42][SPEAKER 2] 失礼します。"""


def ts_to_sec(ts):
    h, m, s = ts.split(':')
    return int(h)*3600 + int(m)*60 + int(s)


pattern = re.compile(r'\[(\d{2}:\d{2}:\d{2})-(\d{2}:\d{2}:\d{2})\]\[(SPEAKER \d+)\] (.+)')

turns = []
for line in transcript.strip().split('\n'):
    m = pattern.match(line)
    if m:
        start, end, speaker, text = m.groups()
        dur = ts_to_sec(end) - ts_to_sec(start)
        turns.append({'start': start, 'end': end, 'speaker': speaker, 'text': text, 'dur': dur})

print('=== Transcript Analysis: script1 (2026-05-01) ===')
print(f'Total turns: {len(turns)}')
print()

# === Q1: Umeda mentions ===
umeda_count = 0
for t in turns:
    cnt = t['text'].count('梅田')
    umeda_count += cnt
    if cnt > 0:
        print(f'  Umeda mention in: [{t["speaker"]}] {t["text"]}  (mentions={cnt})')
print(f'Q1 - 梅田 total mentions: {umeda_count}')
print()

# === Q2: Total call duration ===
first_start = ts_to_sec(turns[0]['start'])
last_end = ts_to_sec(turns[-1]['end'])
total_dur = last_end - first_start
sum_durs = sum(t['dur'] for t in turns)
print(f'Q2 - Total call duration (last_end - first_start): {total_dur}s')
print(f'     Sum of all turn durations: {sum_durs}s')
print(f'     DB metadata duration_seconds: 102s  (stored in transcripts table)')
print()

# === Q3: SPEAKER 1 avg speech duration ===
sp1_turns = [t for t in turns if t['speaker'] == 'SPEAKER 1']
sp1_durs = [t['dur'] for t in sp1_turns]
sp1_avg = sum(sp1_durs) / len(sp1_durs) if sp1_durs else 0
print(f'Q3 - SPEAKER 1 turns: {len(sp1_turns)}')
for i, t in enumerate(sp1_turns):
    print(f'     turn {i+1}: dur={t["dur"]}s  [{t["text"][:40]}]')
print(f'     Sum: {sum(sp1_durs)}s / {len(sp1_durs)} turns = {sp1_avg:.4f}s avg')
print(f'     Rounded: {round(sp1_avg, 2)}s')
print()

# === Q4: Longest utterance ===
max_turn = max(turns, key=lambda t: t['dur'])
print(f'Q4 - Longest utterance: [{max_turn["speaker"]}] dur={max_turn["dur"]}s')
print(f'     Text: {max_turn["text"]}')
print()

# === Q5: Shortest utterance ===
min_dur = min(t['dur'] for t in turns)
min_turns = [t for t in turns if t['dur'] == min_dur]
print(f'Q5 - Shortest utterance(s): dur={min_dur}s ({len(min_turns)} turns)')
for t in min_turns:
    print(f'     [{t["speaker"]}] {t["text"]}')
print()

# === Q6: SPEAKER 1 turn count ===
print(f'Q6 - SPEAKER 1 turn count: {len(sp1_turns)}')
print()

# === Q7: Speaker with most turns ===
speaker_counts = Counter(t['speaker'] for t in turns)
print(f'Q7 - Turn counts per speaker: {dict(speaker_counts)}')
most_speaker = speaker_counts.most_common(1)[0]
print(f'     Most turns: {most_speaker[0]} with {most_speaker[1]} turns')
print()

# === Q8: Number of speakers + topic ===
speakers = set(t['speaker'] for t in turns)
print(f'Q8 - Number of speakers: {len(speakers)} = {sorted(speakers)}')
print(f'     Topic: 梅田さんへの配信(サイズ書)の確認 / スリーラスター社との区別確認')
print()

# === Full turn table ===
print('=== All turns detail ===')
print(f'{"#":>2}  {"Speaker":<10}  {"Start":>8}  {"End":>8}  {"Dur":>4}s  Text')
print('-'*80)
for i, t in enumerate(turns):
    print(f'{i+1:>2}. {t["speaker"]:<10}  {t["start"]:>8}  {t["end"]:>8}  {t["dur"]:>4}s  {t["text"][:45]}')
