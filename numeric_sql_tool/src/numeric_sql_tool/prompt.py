from __future__ import annotations


def build_numeric_intent_prompt(query: str) -> tuple[str, str]:
    system = "Return only JSON. No extra text."
    user = (
        "You are filling a JSON form for numeric aggregation. "
        "Pick values that best match the question. "
        "Allowed values:\n"
        "operator: sum, avg, max, min, count, skip, none\n"
        "target: duration_seconds, meeting_count, time_start_sec, none\n"
        "group_by: none, user_id, day, speaker\n"
        "context_filter: string or null\n\n"
        f"Question: {query}\n"
        "Return JSON for NumericIntent."
    )
    return system, user
