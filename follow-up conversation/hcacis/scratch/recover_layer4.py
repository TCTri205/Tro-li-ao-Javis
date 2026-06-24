import json
import re

log_path = r"C:\Users\Hoa\.gemini\antigravity-ide\brain\c0aeb00e-4b2b-4053-b469-5800e58487cc\.system_generated\logs\transcript.jsonl"

def parse_log():
    with open(log_path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
                if data.get("type") == "VIEW_FILE" and "layer4_generator.py" in data.get("content", "") and "Total Lines" in data.get("content", ""):
                    content = data["content"]
                    
                    code_lines_fixed = []
                    lines = content.split('\n')
                    for l in lines:
                        match = re.match(r'^(\d+):\s?(.*)$', l)
                        if match:
                            code_lines_fixed.append(match.group(2))
                            
                    out_content = "\n".join(code_lines_fixed)
                    if "class Generator:" in out_content:
                        with open(r"d:\javis_text2sql\hcacis\layer4_generator.py", "w", encoding="utf-8") as out_f:
                            out_f.write(out_content)
                        print(f"Recovered layer4_generator.py! Extracted {len(code_lines_fixed)} lines.")
                        return
            except Exception as e:
                pass
    print("Not found")

parse_log()
