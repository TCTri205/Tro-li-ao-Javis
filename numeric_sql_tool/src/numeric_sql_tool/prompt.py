from __future__ import annotations


def build_numeric_intent_prompt(query: str) -> tuple[str, str]:
    system = (
        "You are a routing and intent classifier for a Numeric SQL Tool.\n"
        "Your task is to analyze the user's question and fill in a JSON structure.\n"
        "We support:\n"
        "1. Quantitative aggregations on meeting metadata (meeting count, or sum/avg/max/min of meeting duration in seconds).\n"
        "2. Speaker-specific speaking time (sum/avg of speaking duration per turn for a speaker).\n"
        "3. Turn counts (number of times a speaker spoke in a meeting).\n"
        "4. Keyword/name mention counts (number of times a word, phrase, or person's name was mentioned in the turns).\n"
        "If a question requires semantic understanding, detailed content retrieval (asking 'what', 'who', 'why', 'where', 'how', topics, summaries, action items, reasons, measures, recommendations, opinions), you MUST set operator='skip' and target='none'.\n\n"
        "Return ONLY a JSON block matching the schema of NumericIntent."
    )
    user = (
        "You are filling a JSON form for numeric aggregation. "
        "Pick values that best match the question. "
        "Allowed values:\n"
        "operator: sum, avg, max, min, count, skip, none\n"
        "target: duration_seconds, meeting_count, time_start_sec, speaking_time, turn_count, mention_count, none\n"
        "group_by: none, user_id, day, speaker\n"
        "context_filter: string or null\n"
        "speaker: string or null (extract speaker name, e.g. 'SPEAKER 1', 'サカモト', 'クマガイ' if the query asks about speaker turn count or speaking time)\n"
        "keyword: string or null (extract keyword to search for, e.g. '梅田', '14日水曜日', '会社名' if the query asks about keyword mention count)\n\n"
        f"Question: {query}\n"
        "Return JSON for NumericIntent."
    )
    return system, user
