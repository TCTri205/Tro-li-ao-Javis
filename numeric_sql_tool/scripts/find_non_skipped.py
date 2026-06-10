from pathlib import Path
import re

content = Path("d:/VJ/Tro-li-ao-Javis/numeric_sql_tool/eval_v2/executed_print_all.txt").read_text(encoding="utf-8")
blocks = content.split("Row ")

out_lines = []
for block in blocks:
    if not block.strip():
        continue
    lines = block.splitlines()
    header = lines[0]
    result_line = ""
    sql_line = ""
    for line in lines:
        if "Result:" in line:
            result_line = line
        if "SQL:" in line:
            sql_line = line
            
    if "operator=skip" not in result_line:
        out_lines.append(f"Row {header}")
        out_lines.append(f"  {result_line.strip()}")
        out_lines.append(f"  {sql_line.strip()}")
        out_lines.append("-" * 50)

Path("d:/VJ/Tro-li-ao-Javis/numeric_sql_tool/eval_v2/non_skipped_list.txt").write_text("\n".join(out_lines), encoding="utf-8")
print("Done")
