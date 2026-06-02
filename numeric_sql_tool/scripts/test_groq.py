
import asyncio
import os
from dotenv import load_dotenv
import httpx
import json
from pydantic import BaseModel, Field
from typing import Literal

class NumericIntent(BaseModel):
    operator: Literal["sum", "avg", "max", "min", "count", "skip", "none"] = "none"
    target: Literal["duration_seconds", "meeting_count", "time_start_sec", "none"] = "none"
    group_by: Literal["none", "user_id", "day", "speaker"] = "none"
    context_filter: str | None = None

async def test_groq():
    load_dotenv()
    keys_str = os.getenv("GROQ_API_KEYS", "")
    keys = [k.strip() for k in keys_str.split(",") if k.strip()]
    if not keys:
        api_key = os.getenv("GROQ_API_KEY")
        if api_key:
            keys = [api_key]
            
    if not keys:
        print("No Groq API keys found")
        return

    model = "llama-3.3-70b-versatile"
    url = "https://api.groq.com/openai/v1/chat/completions"
    
    schema_json = json.dumps(NumericIntent.model_json_schema())
    system = "Return only JSON. No extra text."
    modified_system = (
        f"{system}\n\n"
        "You must return a valid JSON object strictly matching this JSON Schema:\n"
        f"{schema_json}\n\n"
        "Do not include any extra explanation or markdown block."
    )
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": modified_system},
            {"role": "user", "content": "How many meetings were held today?"}
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"}
    }
    
    for i, api_key in enumerate(keys):
        key_display = f"{api_key[:6]}...{api_key[-4:]}"
        print(f"Testing key {i+1}/{len(keys)}: {key_display}")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                print(f"  Status Code: {response.status_code}")
                if response.status_code != 200:
                    print(f"  Error: {response.text}")
            except Exception as exc:
                print(f"  Exception: {exc}")

if __name__ == "__main__":
    asyncio.run(test_groq())
