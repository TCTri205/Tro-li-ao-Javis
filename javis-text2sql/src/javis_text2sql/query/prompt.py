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
        "Anh Bình có cam kết gì chưa hoàn thành?",
        "SELECT person, action, deadline FROM v_commitments WHERE person ILIKE '%Bình%' AND status = 'pending';",
    ),
    (
        "Chi phí điện trong các cuộc họp tháng này là bao nhiêu?",
        "SELECT SUM(amount_value) AS total_amount FROM v_amounts WHERE amount_context ILIKE '%điện%' AND meeting_date >= DATE '2026-05-01';",
    ),
    (
        "Liệt kê tất cả action item quan trọng.",
        "SELECT meeting_title, action_item_text, importance_score FROM v_action_items WHERE importance_score >= 4 ORDER BY meeting_date DESC;",
    ),
    (
        "Có những câu hỏi nào chưa được trả lời?",
        "SELECT meeting_title, question_text, importance_score FROM v_open_questions ORDER BY importance_score DESC;",
    ),
    (
        "Ai nhắc đến ngân sách 4,500万円?",
        "SELECT speaker, turn_content, meeting_date FROM v_speaker_turns WHERE turn_content ILIKE '%4,500%' OR turn_content ILIKE '%４,５００%';",
    ),
    (
        "Tổng ngân sách JPY được nhắc tới là bao nhiêu?",
        "SELECT SUM(amount_value) AS total_amount, amount_currency FROM v_amounts WHERE amount_currency = 'JPY' GROUP BY amount_currency;",
    ),
    (
        "Những cam kết đến hạn trước 2026-06-01 là gì?",
        "SELECT person, action, deadline, deadline_date FROM v_commitments WHERE deadline_date < DATE '2026-06-01';",
    ),
    (
        "VJ Technologies xuất hiện trong những chủ đề nào?",
        "SELECT meeting_title, topic, source_type FROM v_topics WHERE topic ILIKE '%VJ Technologies%';",
    ),
    (
        "Thống kê số cam kết theo trạng thái.",
        "SELECT status, COUNT(*) AS commitment_count FROM v_commitments GROUP BY status ORDER BY commitment_count DESC;",
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
        "SELECT DISTINCT meeting_title, topic FROM v_topics WHERE topic ILIKE '%AJ%' OR topic ILIKE '%VJ%' OR topic ILIKE '%ONE Financial%';",
    ),
    (
        "重要度が高くネガティブな発言を表示してください。",
        "SELECT meeting_title, content, importance_score FROM v_statements WHERE sentiment = 'negative' AND importance_score >= 4;",
    ),
    (
        "Mỗi người có bao nhiêu lượt phát ngôn?",
        "SELECT speaker, COUNT(*) AS turn_count FROM v_speaker_turns GROUP BY speaker ORDER BY turn_count DESC;",
    ),
]


def render_few_shots() -> str:
    return "\n\n".join(f"Question: {question}\nSQL: {sql}" for question, sql in FEW_SHOT_EXAMPLES)


def build_sql_system_prompt(reference_date: date, entity_map: dict[str, str] | None = None) -> str:
    entity_lines = "\n".join(f"- {alias} => {canonical}" for alias, canonical in (entity_map or {}).items())
    if not entity_lines:
        entity_lines = "- None"
    return f"""You are an expert PostgreSQL generator for the Javis Text-to-SQL tool.
Return exactly one read-only SELECT statement. Do not include markdown fences.
Only query these allowed semantic views: {", ".join(ALLOWED_VIEWS)}.
Do not query base tables. Do not write INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, CALL, COPY, or SET.
Today's reference date: {reference_date.isoformat()}.
Mapped entities:
{entity_lines}

Few-shot examples:
{render_few_shots()}
"""


def build_refine_prompt(reference_date: date) -> str:
    return f"""You are asked to refine a failed PostgreSQL SELECT query for Javis.
Fix the SQL using only allowed views: {", ".join(ALLOWED_VIEWS)}.
Return exactly one SELECT statement and no markdown.
Today's reference date: {reference_date.isoformat()}.
"""
