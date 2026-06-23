import os
import csv
import sys
import time
from dotenv import load_dotenv
from groq import Groq
from openai import OpenAI

sys.stdout.reconfigure(encoding='utf-8')

# Load env variables from root .env
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(dotenv_path)

csv_path = r"D:\VJ\Tro-li-ao-Javis\multi-turn-context-manager\reports\tests\test_summary_06_22.csv"

# Initialize LLM Clients
groq_keys_str = os.getenv("GROQ_API_KEYS", "")
groq_keys = [k.strip() for k in groq_keys_str.split(",") if k.strip()]
groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

qwen_api_key = os.getenv("JAVIS_QWEN_API_KEY")
qwen_base_url = os.getenv("JAVIS_QWEN_BASE_URL")
qwen_model = os.getenv("JAVIS_QWEN_MODEL")

def translate_text(text: str) -> str:
    if not text or text.strip() == "":
        return text
    
    # Check if the text is a system list of strings (e.g. topic list)
    if text.strip().startswith("[") and text.strip().endswith("]") and "topic" in text:
        return text
        
    if text.strip() in ["TimeoutError triggered", "Multiple Answers", "5 answers received", "PASS", "FAIL"]:
        mapping = {
            "TimeoutError triggered": "Kích hoạt lỗi TimeoutError",
            "Multiple Answers": "Nhiều phản hồi",
            "5 answers received": "Đã nhận 5 phản hồi",
            "PASS": "ĐẠT",
            "FAIL": "THẤT BẠI"
        }
        return mapping.get(text.strip(), text)
    
    system_prompt = (
        "You are an expert translator translating Japanese to Vietnamese.\n"
        "Please strictly adhere to the following rules:\n"
        "1. Translate Japanese personal names using their standard Romaji transliteration (e.g. '島田' -> 'Shimada', '中原' -> 'Nakahara', '中原凛花' -> 'Nakahara Rinka', '中岡' -> 'Nakaoka', '山下' -> 'Yamashita', '伊藤' -> 'Ito', '辻' -> 'Tsuji', '石原' -> 'Ishihara', 'サカモト' -> 'Sakamoto', 'クマガイ' -> 'Kumagai', 'カセ/加瀬' -> 'Kase', '横堀' -> 'Yokohori', '島田' -> 'Shimada', '熊田' -> 'Kumada'). Do NOT use Sino-Vietnamese names (e.g. do NOT use 'Trung Nguyên', 'Đảo Điền') and do NOT use hybrid characters (e.g. do NOT use 'Đảo田', 'Trung 岡', 'Anhとう').\n"
        "2. Translate 'AJテクノロジーズ' as 'AJ Technologies' (do NOT translate as 'AJ Công nghệ').\n"
        "3. Translate 'Multiple Answers' as 'Nhiều phản hồi' or 'Nhiều câu trả lời' (do NOT translate as 'Đảng đáp án').\n"
        "4. Keep the exact structural format (starting with 'T1:', 'T2:', preserving the pipes '|' and line breaks).\n"
        "5. Do NOT hallucinate or change names (e.g. do not translate '伊藤' to 'Nakahara Rinka').\n"
        "6. Do not include any chat preamble or explanation. Output ONLY the translated text."
    )
    
    prompt = (
        f"Translate the following text into natural, accurate Vietnamese according to the system rules:\n\n{text}"
    )
    
    # Try Groq first
    for key in groq_keys:
        try:
            client = Groq(api_key=key)
            completion = client.chat.completions.create(
                model=groq_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0
            )
            ans = completion.choices[0].message.content.strip()
            if "<think>" in ans or "</think>" in ans:
                if "</think>" in ans:
                    ans = ans.split("</think>")[-1].strip()
            return ans
        except Exception as e:
            print(f"Groq API key error with {key[:10]}...: {e}")
            time.sleep(0.5)
            
    # Try Qwen gateway as fallback
    if qwen_api_key and qwen_base_url:
        try:
            client = OpenAI(api_key=qwen_api_key, base_url=qwen_base_url)
            completion = client.chat.completions.create(
                model=qwen_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0
            )
            ans = completion.choices[0].message.content.strip()
            if "<think>" in ans or "</think>" in ans:
                if "</think>" in ans:
                    ans = ans.split("</think>")[-1].strip()
            return ans
        except Exception as e:
            print(f"Qwen API error: {e}")
            
    raise RuntimeError("Failed to translate using all available LLM options.")

# Read CSV
with open(csv_path, 'r', encoding='utf-8') as f:
    reader = csv.reader(f)
    rows = list(reader)

if not rows:
    print("CSV is empty!")
    sys.exit(1)

header = rows[0]
try:
    actual_idx = header.index("Actual Result (Captured Answer)")
    translation_idx = header.index("Dịch Actual Result")
except ValueError:
    print("Could not find required columns in header!")
    sys.exit(1)

new_rows = [header]

for i in range(1, len(rows)):
    row = rows[i]
    if not row:
        continue
    # Ensure row has enough columns
    while len(row) < len(header):
        row.append("")
        
    actual_val = row[actual_idx]
    print(f"\n--- Translating Row {i} (Scenario: {row[2]}) ---")
    print(f"Original: {actual_val[:100]}...")
    
    translated_val = translate_text(actual_val)
    print(f"Refined: {translated_val[:100]}...")
    
    # Overwrite the translation column value
    row[translation_idx] = translated_val
    new_rows.append(row)
    time.sleep(0.5)

# Write back to CSV
with open(csv_path, 'w', encoding='utf-8', newline='') as f:
    writer = csv.writer(f)
    writer.writerows(new_rows)

print("\nDone! Successfully refined all translations in the CSV.")
