import pandas as pd
import re
import os

def md_table_to_xlsx(md_path, xlsx_path):
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find the table content
    # Look for the header line and the separator line
    lines = content.split('\n')
    table_lines = []
    in_table = False
    
    for line in lines:
        if line.strip().startswith('|') and '---' not in line:
            if not in_table:
                # Check if next line is a separator
                idx = lines.index(line)
                if idx + 1 < len(lines) and '---|' in lines[idx+1]:
                    in_table = True
                    # This is the header
                    headers = [h.strip() for h in line.strip('|').split('|')]
                    continue
            if in_table:
                table_lines.append(line)
        elif in_table:
            # Table ended or empty line
            if line.strip() == '':
                continue
            # Some non-table line
            # Check if it's still part of the table (like multi-line cells, though MD tables usually aren't)
            # For this specific report, we assume one table.
            pass

    # Re-extract headers to be sure
    # The first line starting with | that is followed by |---| is the header
    header_line = ""
    start_idx = 0
    for i, line in enumerate(lines):
        if line.strip().startswith('|') and i+1 < len(lines) and '---|' in lines[i+1]:
            header_line = line
            start_idx = i + 2
            break
            
    headers = [h.strip() for h in header_line.strip('|').split('|')]
    
    data = []
    for line in lines[start_idx:]:
        if line.strip().startswith('|'):
            row = [cell.strip() for cell in line.strip('|').split('|')]
            # Some cells might have | character escaped as \|
            # Simple split('|') will break if there are \| inside cells
            # But the table uses | as separator.
            # Let's handle escaped pipes if necessary, but split('|') usually works if the number of columns matches.
            if len(row) == len(headers):
                data.append(row)
            elif len(row) > len(headers):
                # Probably escaped pipes. Let's try a more robust split
                # This is common in SQL queries in the report
                row = re.split(r'(?<!\\)\|', line.strip('|'))
                row = [r.strip().replace(r'\|', '|') for r in row]
                if len(row) == len(headers):
                    data.append(row)
        # Don't break early, collect all table rows in the file
    
    df = pd.DataFrame(data, columns=headers)
    
    # Remove "Cú pháp mong muốn" column
    if "Cú pháp mong muốn" in df.columns:
        df = df.drop(columns=["Cú pháp mong muốn"])
    
    # Save to Excel
    df.to_excel(xlsx_path, index=False)
    print(f"Successfully converted {md_path} to {xlsx_path}")

if __name__ == "__main__":
    md_file = r'd:\VJ\Tro-li-ao-Javis\numeric_sql_tool\eval\evaluation_report_200_honest.md'
    xlsx_file = r'd:\VJ\Tro-li-ao-Javis\numeric_sql_tool\eval\evaluation_report_200_honest.xlsx'
    md_table_to_xlsx(md_file, xlsx_file)
