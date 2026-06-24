import re
from typing import Dict, Any, List
from .models import TurnState
from .llm_client import LLMClient

class AnswerGenerator:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def _sanitize_history(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        sanitized = []
        for msg in messages:
            content = msg.get("content", "")
            if content is None:
                content = ""
            if msg["role"] == "assistant":
                # Remove SQL blocks to prevent hallucinating SQL for RAG queries
                content = content.split('**[LLM Generated SQL]**')[0].split('**[Pipeline Generated SQL]**')[0].strip()
            sanitized.append({"role": msg["role"], "content": content})
        return sanitized

    async def generate(self, turn_state: TurnState) -> TurnState:
        system_prompt = """You are a helpful Japanese AI assistant representing the HCACIS system.
You answer user questions based on the retrieved data and current context.
If no retrieved data is available or insufficient, answer based on your general knowledge but DO NOT hallucinate meeting details.
ALWAYS answer in Japanese.

Retrieved Data:
{retrieved_data}

Plan Executed: {plan_executed}
"""
        
        system_content = system_prompt.format(
            retrieved_data=turn_state.retrieved_data or "None",
            plan_executed=turn_state.detector_output.intent_category if turn_state.detector_output else "none"
        )
        
        sanitized_messages = self._sanitize_history(turn_state.messages)
        
        history_str = ""
        for m in sanitized_messages:
            role = "User" if m['role'] == 'user' else "Assistant"
            history_str += f"{role}: {m['content']}\n"
            
        user_query = turn_state.current_query
        user_prompt = f"Chat History:\n{history_str}\n\nUser Question:\n{user_query}"
        
        answer = await self.llm_client.generate_text(system_content, user_prompt)
        
        # Append SQL queries to the answer if they exist in retrieved_data
        if isinstance(turn_state.retrieved_data, dict) and turn_state.detector_output and turn_state.detector_output.intent_category == "sql":
            sql_blocks = ""
            metadata = turn_state.retrieved_data.get("metadata", {})
            
            # 1. Pipeline Generated SQL
            if "sql" in metadata and metadata["sql"]:
                sql_blocks += f"\n\n**[Pipeline Generated SQL]**\n```sql\n{metadata['sql']}\n```"
                
            # 2. LLM Generated SQL (via Ollama)
            sql_prompt = (
                "You are an expert PostgreSQL developer. Write a SQL query to answer the user's question based on these tables:\n"
                "1. transcripts(id uuid, meeting_date date, duration_seconds float, user_id uuid, summary text, raw_text text)\n"
                "2. chunks_turn(id uuid, transcript_id uuid, speaker text, time_start_sec float, time_end_sec float, text text)\n"
                "Return ONLY the SQL block starting with ```sql and ending with ```. No explanations."
            )
            
            # Use the rewritten query for better SQL generation, fallback to current_query
            query_to_sql = turn_state.detector_output.rewritten_standalone_query if turn_state.detector_output and turn_state.detector_output.rewritten_standalone_query else user_query
            
            llm_sql = await self.llm_client.generate_text(sql_prompt, f"Question: {query_to_sql}")
            
            # Format nicely
            llm_sql = llm_sql.strip()
            # Remove any markdown artifacts if model included it differently
            if "```sql" in llm_sql:
                # Extract just the block
                import re
                match = re.search(r'```sql\n(.*?)\n```', llm_sql, re.DOTALL)
                if match:
                    llm_sql = match.group(0)
            elif not llm_sql.startswith("```sql"):
                llm_sql = "```sql\n" + llm_sql + "\n```"
                
            sql_blocks = f"\n\n**[LLM Generated SQL]**\n{llm_sql}" + sql_blocks
            
            answer += sql_blocks
        
        turn_state.messages.append({"role": "user", "content": turn_state.current_query})
        turn_state.messages.append({"role": "assistant", "content": answer})
        turn_state.final_answer = answer
        return turn_state
