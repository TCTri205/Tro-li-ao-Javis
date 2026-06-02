from __future__ import annotations


def build_numeric_intent_prompt(query: str) -> tuple[str, str]:
    system = (
        "You are a routing and intent classifier for a Numeric SQL Tool.\n"
        "Your task is to analyze the user's question and fill in a JSON structure.\n"
        "CRITICAL: We only support basic quantitative aggregations on meeting metadata (meeting count, or sum/avg/max/min of meeting duration in seconds).\n"
        "If a question requires semantic understanding, detailed content retrieval, comparison of multiple metrics, turn-level timestamps, or is not a quantitative query, you MUST set operator='skip' and target='none'.\n\n"
        "Rules for SKIP:\n"
        "- Qualitative/semantic questions (asking 'what', 'who', 'why', 'where', 'how', topics, summaries, action items, reasons, measures, recommendations, opinions).\n"
        "- Specific detail values discussed IN the meetings (e.g., budget amounts, prices, costs, percentages, achievement rates, number of companies/engineers, weather, general facts).\n"
        "- Turn-level timestamps or speech timing (e.g., 'what minute/second did X speak', 'when did Y say Z').\n"
        "- Non-questions (e.g., greetings 'hello', commands 'delete meeting', single words 'meeting').\n"
        "- Complex comparisons or multi-metric queries (e.g., comparing this week and last week, asking for both count and duration, difference between months).\n"
        "- Asking for a specific meeting identity or list based on content (e.g., 'which meeting had the most participants', 'tell me the meetings about X').\n"
        "\n"
        "Return ONLY a JSON block matching the schema of NumericIntent."
    )
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
