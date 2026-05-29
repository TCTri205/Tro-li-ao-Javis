from __future__ import annotations

from datetime import date


ALLOWED_VIEWS = [
    "v_topics",
    "v_commitments",
    "v_amounts",
    "v_action_items",
    "v_open_questions",
    "v_statements",
    "v_dates",
    "v_speaker_turns",
]

FEW_SHOT_EXAMPLES = [
    (
        "山下さんの未完了のコミットメントは何ですか？",
        "SELECT person, action, deadline FROM v_commitments WHERE person ILIKE '%山下%' AND status = 'pending';",
    ),
    (
        "今月の会議での電気代の費用 is electricity? (今月の会議での電気代の費用はいくらですか？)",
        "SELECT SUM(amount_value) AS total_amount FROM v_amounts WHERE amount_context ILIKE '%電気%' AND meeting_date >= DATE '2026-05-01';",
    ),
    (
        "重要なアクションアイテムをすべて一覧表示してください。",
        "SELECT meeting_title, action_item_text, importance_score FROM v_action_items WHERE importance_score >= 4 ORDER BY meeting_date DESC;",
    ),
    (
        "未回答の質問はどのようなものがありますか？",
        "SELECT meeting_title, question_text, importance_score FROM v_open_questions ORDER BY importance_score DESC;",
    ),
    (
        "誰が4,500万円の予算について言及しましたか？",
        "SELECT speaker, turn_content, meeting_date FROM v_speaker_turns WHERE turn_content ILIKE '%4,500%' OR turn_content ILIKE '%４,５００%';",
    ),
    (
        "言及された日本円（JPY）の総予算はいくらですか？",
        "SELECT SUM(amount_value) AS total_amount FROM v_amounts WHERE amount_currency = 'JPY';",
    ),
    (
        "2026-06-01より前に期限が切れるコミットメントは何ですか？",
        "SELECT person, action, deadline, deadline_date FROM v_commitments WHERE deadline_date < DATE '2026-06-01';",
    ),
    (
        "VJ Technologies はどのようなトピックで言及されていますか？",
        "SELECT meeting_title, topic FROM v_topics WHERE topic ILIKE '%VJ Technologies%' AND source_type = 'topic';",
    ),
    (
        "ステータスごとのコミットメント数を集計してください。",
        "SELECT status, COUNT(1) AS commitment_count FROM v_commitments GROUP BY status ORDER BY commitment_count DESC;",
    ),
    (
        "今週の期限があるタスクを一覧してください。",
        "SELECT person, action, deadline FROM v_commitments WHERE deadline ILIKE '%今週%';",
    ),
    (
        "予算に関する金額を合計してください。",
        "SELECT SUM(amount_value) AS total_budget FROM v_amounts WHERE amount_context ILIKE '%予算%';",
    ),
    (
        "５月３０日に関する予定はありますか？",
        "SELECT meeting_title, date_raw_text, date_resolved FROM v_dates WHERE date_raw_text ILIKE '%５月３０日%' OR date_raw_text ILIKE '%5月30日%';",
    ),
    (
        "AJ Technologies と関係する会社をリストしてください。",
        "SELECT DISTINCT topic FROM v_topics WHERE (topic ILIKE '%AJ%' OR topic ILIKE '%VJ%' OR topic ILIKE '%ONE Financial%') AND source_type = 'entity';",
    ),
    (
        "重要 độ cao? (重要度が高くネガティブな発言を表示してください。)",
        "SELECT meeting_title, content, importance_score FROM v_statements WHERE sentiment = 'negative' AND importance_score >= 4;",
    ),
    (
        "各発言者の発言数はそれぞれ何回ですか？",
        "SELECT speaker, COUNT(1) AS turn_count FROM v_speaker_turns GROUP BY speaker ORDER BY turn_count DESC;",
    )
]


def render_few_shots() -> str:
    return "\n\n".join(f"Question: {question}\nSQL: {sql}" for question, sql in FEW_SHOT_EXAMPLES)


def build_sql_system_prompt(
    reference_date: date,
    entity_map: dict[str, str] | None = None,
    few_shots: list[tuple[str, str]] | None = None,
) -> str:
    entity_lines = "\n".join(f"- {alias} => {canonical}" for alias, canonical in (entity_map or {}).items())
    if not entity_lines:
        entity_lines = "- None"
    
    shots = few_shots if few_shots is not None else FEW_SHOT_EXAMPLES
    rendered_few_shots = "\n\n".join(f"Question: {question}\nSQL: {sql}" for question, sql in shots)

    return f"""You are an expert PostgreSQL generator for the Javis Text-to-SQL tool.
Return exactly one read-only SELECT statement. Do not include markdown fences.
Today's reference date: {reference_date.isoformat()}.

Allowed views and their columns (ONLY query these):
- v_topics (meeting_id, meeting_title, meeting_date, passage_id, topic, source_type)
  * MUST filter by `source_type = 'topic'` when query is about meeting topics or titles (e.g. "トピック").
  * MUST filter by `source_type = 'entity'` when query is about named entities/companies (e.g. "エンティティ").
- v_commitments (meeting_id, meeting_title, meeting_date, passage_id, commitment_id, person, action, deadline, deadline_date, status)
  * Column `status` only accepts 'pending', 'done', or 'cancelled'. Never use 'completed' or 'success'. Use 'done' for completed commitments.
  * WARNING: Do NOT use the substring 'completed' in any column aliases (e.g., use `done_commitments` or `done_commitment_count` instead of `completed_commitment_count` to avoid validation errors).
- v_amounts (meeting_id, meeting_title, meeting_date, passage_id, amount_value, amount_unit, amount_currency, amount_context)
  * Note: Use `amount_unit` (there is no column named `unit`).
- v_action_items (meeting_id, meeting_title, meeting_date, passage_id, action_item_text, importance_score)
- v_open_questions (meeting_id, meeting_title, meeting_date, passage_id, question_text, importance_score)
- v_statements (meeting_id, meeting_title, meeting_date, passage_id, turn_types, has_action_item, has_question, sentiment, importance_score, content)
- v_dates (meeting_id, meeting_title, meeting_date, passage_id, date_raw_text, date_resolved, confidence)
- v_speaker_turns (meeting_id, meeting_title, meeting_date, speaker, turn_content, timestamp, turn_types, sentiment, importance_score)

STRICT SCHEMA RULES:
1. NO passage_id in v_speaker_turns: The view `v_speaker_turns` DOES NOT have a `passage_id` column! Never SELECT or filter by `passage_id` when querying `v_speaker_turns`.
2. NO source_type except in v_topics: Only the view `v_topics` has the `source_type` column! Never refer to `source_type` in any other views.
3. ARRAY type for turn_types: The `turn_types` column in both `v_statements` and `v_speaker_turns` is a text ARRAY (text[]). You cannot use direct string comparisons (e.g. `turn_types = 'statement'` or `turn_types LIKE ...`). Instead, you MUST use PostgreSQL array operators, for example: `'statement' = ANY(turn_types)`.
4. Japanese terminologies mapping:
   - "発話" (speaker turns/utterance) ALWAYS maps to `v_speaker_turns`. Use it when counting utterances per speaker or finding who said what.
   - "発言" (statement/remark/sentiment) ALWAYS maps to `v_statements`. Use it when the query asks about statements/remarks with emotions/sentiments or importance scores (e.g. "感情がneutralの発言", "重要度スコアが...の発言").
5. Anti-patterns: NEVER use `COUNT(*)` or `SELECT *`. Always use explicit column names or `COUNT(1)` to prevent parser warnings.
6. Uniqueness: When a query asks for "different" (異なる) items, always use `SELECT DISTINCT` at the top level or `SELECT DISTINCT COUNT(...)`. If distinct results are not explicitly requested, do NOT use `DISTINCT`.
7. Aggregations: Avoid grouping by constant filter values. For example, if you filter by `amount_currency = 'JPY'`, do not include `GROUP BY amount_currency`.
8. SELECT DISTINCT with ORDER BY: If you use `SELECT DISTINCT` and also need to `ORDER BY` a column (e.g. importance_score), that sorted column MUST be included in the SELECT clause (e.g. `SELECT DISTINCT question_text, importance_score ... ORDER BY importance_score`). Otherwise, PostgreSQL will throw an execution error.

Mapped entities:
{entity_lines}

Few-shot examples:
{rendered_few_shots}
"""


def build_refine_prompt(reference_date: date) -> str:
    return f"""You are asked to refine a failed PostgreSQL SELECT query for Javis.
Fix the SQL using only allowed views: {", ".join(ALLOWED_VIEWS)}.
Return exactly one SELECT statement and no markdown.
Today's reference date: {reference_date.isoformat()}.

Allowed views and their columns (ONLY query these):
- v_topics (meeting_id, meeting_title, meeting_date, passage_id, topic, source_type)
  * MUST filter by `source_type = 'topic'` when query is about meeting topics or titles (e.g. "トピック").
  * MUST filter by `source_type = 'entity'` when query is about named entities/companies (e.g. "エンティティ").
- v_commitments (meeting_id, meeting_title, meeting_date, passage_id, commitment_id, person, action, deadline, deadline_date, status)
  * Column `status` only accepts 'pending', 'done', or 'cancelled'. Never use 'completed' or 'success'. Use 'done' for completed commitments.
  * WARNING: Do NOT use the substring 'completed' in any column aliases (e.g., use `done_commitments` or `done_commitment_count` instead of `completed_commitment_count` to avoid validation errors).
- v_amounts (meeting_id, meeting_title, meeting_date, passage_id, amount_value, amount_unit, amount_currency, amount_context)
  * Note: Use `amount_unit` (there is no column named `unit`).
- v_action_items (meeting_id, meeting_title, meeting_date, passage_id, action_item_text, importance_score)
- v_open_questions (meeting_id, meeting_title, meeting_date, passage_id, question_text, importance_score)
- v_statements (meeting_id, meeting_title, meeting_date, passage_id, turn_types, has_action_item, has_question, sentiment, importance_score, content)
- v_dates (meeting_id, meeting_title, meeting_date, passage_id, date_raw_text, date_resolved, confidence)
- v_speaker_turns (meeting_id, meeting_title, meeting_date, speaker, turn_content, timestamp, turn_types, sentiment, importance_score)

STRICT SCHEMA RULES:
1. NO passage_id in v_speaker_turns: The view `v_speaker_turns` DOES NOT have a `passage_id` column! Never SELECT or filter by `passage_id` when querying `v_speaker_turns`.
2. NO source_type except in v_topics: Only the view `v_topics` has the `source_type` column! Never refer to `source_type` in any other views.
3. ARRAY type for turn_types: The `turn_types` column in both `v_statements` and `v_speaker_turns` is a text ARRAY (text[]). You cannot use direct string comparisons (e.g. `turn_types = 'statement'` or `turn_types LIKE ...`). Instead, you MUST use PostgreSQL array operators, for example: `'statement' = ANY(turn_types)`.
4. Japanese terminologies mapping:
   - "発話" (speaker turns/utterance) ALWAYS maps to `v_speaker_turns`. Use it when counting utterances per speaker or finding who said what.
   - "発言" (statement/remark/sentiment) ALWAYS maps to `v_statements`. Use it when the query asks about statements/remarks with emotions/sentiments or importance scores (e.g. "感情がneutralの発言", "重要度スコアが...の発言").
5. Anti-patterns: NEVER use `COUNT(*)` or `SELECT *`. Always use explicit column names or `COUNT(1)`.
6. Uniqueness: Use `SELECT DISTINCT` or `SELECT DISTINCT COUNT(...)` when "different" (異なる) is mentioned. If distinct results are not explicitly requested, do NOT use `DISTINCT`.
7. Aggregations: Avoid grouping by constant filter values.
8. SELECT DISTINCT with ORDER BY: If you use `SELECT DISTINCT` and also need to `ORDER BY` a column (e.g. importance_score), that sorted column MUST be included in the SELECT clause (e.g. `SELECT DISTINCT question_text, importance_score ... ORDER BY importance_score`). Otherwise, PostgreSQL will throw an execution error.
"""
