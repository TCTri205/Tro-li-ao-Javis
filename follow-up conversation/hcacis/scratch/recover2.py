import json
import re

log_path = r"C:\Users\Hoa\.gemini\antigravity-ide\brain\c0aeb00e-4b2b-4053-b469-5800e58487cc\.system_generated\logs\transcript.jsonl"

def parse_log():
    with open(log_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
                if data.get("type") == "VIEW_FILE" and "heuristics.py" in data.get("content", "") and "Total Lines: 466" in data.get("content", ""):
                    content = data["content"]
                    
                    # We need to extract the code.
                    # The output format is:
                    # <number>: <line of code>
                    
                    code_lines = []
                    lines = content.split('\n')
                    for l in lines:
                        # Match things like "1: from __future__ import annotations"
                        # or "466:     return intent"
                        match = re.match(r'^(\d+):\s(.*)$', l)
                        if match:
                            code_lines.append(match.group(2))
                        elif l == "":
                            # empty lines are skipped by the regex but we might need them?
                            # wait, original empty lines are printed as "15: "
                            pass
                            
                    # Let's fix empty lines
                    code_lines_fixed = []
                    for l in lines:
                        match = re.match(r'^(\d+):\s?(.*)$', l)
                        if match:
                            code_lines_fixed.append(match.group(2))
                            
                    out_content = "\n".join(code_lines_fixed)
                    with open(r"d:\javis_text2sql\numeric_sql_tool_v2\src\numeric_sql_tool\heuristics.py", "w", encoding="utf-8") as out_f:
                        out_f.write(out_content)
                    print(f"Recovered heuristics.py! Extracted {len(code_lines_fixed)} lines.")
                    return
            except json.JSONDecodeError:
                pass
            except Exception as e:
                print(e)
                pass
    print("Not found")

parse_log()
