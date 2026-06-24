import json

log_path = r"C:\Users\Hoa\.gemini\antigravity-ide\brain\c0aeb00e-4b2b-4053-b469-5800e58487cc\.system_generated\logs\transcript.jsonl"
heuristics_content = ""

with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            data = json.loads(line)
            if data.get("type") == "VIEW_FILE" and "heuristics.py" in data.get("content", "") and "Total Lines: 466" in data.get("content", ""):
                content = data["content"]
                # Extract the code between the intro text and the outro text
                lines = content.split('\n')
                code_lines = []
                for l in lines:
                    if l.startswith("The following code") or l.startswith("File Path:") or l.startswith("Created At:") or l.startswith("Completed At:") or l.startswith("Total ") or l.startswith("Showing ") or l.startswith("The above content"):
                        continue
                    # Remove the line number prefix like "1: "
                    parts = l.split(": ", 1)
                    if len(parts) == 2 and parts[0].isdigit():
                        code_lines.append(parts[1])
                heuristics_content = "\n".join(code_lines)
                break
        except Exception as e:
            pass

if heuristics_content:
    with open(r"d:\javis_text2sql\numeric_sql_tool_v2\src\numeric_sql_tool\heuristics.py", "w", encoding="utf-8") as out:
        out.write(heuristics_content)
    print("Recovered heuristics.py successfully!")
else:
    print("Could not find the content in the transcript.")
