import re
import os

def md_to_html(md_path, html_path):
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Simple MD to HTML conversion
    
    # Title
    content = re.sub(r'^# (.*)', r'<h1>\1</h1>', content, flags=re.MULTILINE)
    # Sections
    content = re.sub(r'^## (.*)', r'<h2>\1</h2>', content, flags=re.MULTILINE)
    
    # Lists
    content = re.sub(r'^- \*\*(.*)\*\*: (.*)', r'<li><strong>\1</strong>: \2</li>', content, flags=re.MULTILINE)
    # Wrap list items in <ul> (very basic)
    content = re.sub(r'((?:<li>.*</li>\n?)+)', r'<ul>\1</ul>', content)

    # Table conversion
    def convert_table(match):
        rows = match.group(0).strip().split('\n')
        if len(rows) < 3: return match.group(0)
        
        html_table = '<div class="table-container"><table>\n'
        
        # Header
        header_cols = [c.strip() for c in rows[0].strip('|').split('|')]
        html_table += '  <thead>\n    <tr>\n'
        for col in header_cols:
            html_table += f'      <th>{col}</th>\n'
        html_table += '    </tr>\n  </thead>\n'
        
        # Body
        html_table += '  <tbody>\n'
        for row in rows[2:]:
            # Use regex to split by | but NOT by \|
            cols = [c.strip() for c in re.split(r'(?<!\\)\|', row.strip('|'))]
            html_table += '    <tr>\n'
            for col in cols:
                # Special styling for Đúng/Sai
                cell_content = col
                if '🟢 **Đúng**' in col:
                    cell_content = col.replace('🟢 **Đúng**', '<span class="status-pass">🟢 Đúng</span>')
                elif '🔴 **Sai**' in col:
                    cell_content = col.replace('🔴 **Sai**', '<span class="status-fail">🔴 Sai</span>')
                
                # Unescape pipes for display
                cell_content = cell_content.replace(r'\|', '|')
                
                # Replace markdown bold in cells
                cell_content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', cell_content)
                # Handle line breaks in cells (the <br> is already there in MD, but we might need to ensure it's kept)
                
                # Format SQL blocks in cells
                if cell_content.startswith('`') and cell_content.endswith('`'):
                    cell_content = f'<code>{cell_content.strip("`")}</code>'
                
                html_table += f'      <td>{cell_content}</td>\n'
            html_table += '    </tr>\n'
        html_table += '  </tbody>\n'
        html_table += '</table></div>'
        return html_table

    # Find the table and convert it
    table_pattern = re.compile(r'\|.*\|(?:\n\|.*\|)+', re.MULTILINE)
    content = table_pattern.sub(convert_table, content)

    html_template = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Báo cáo Đánh giá chi tiết</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f9f9f9;
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
            text-align: center;
        }}
        h2 {{
            color: #2980b9;
            margin-top: 30px;
            border-left: 5px solid #3498db;
            padding-left: 10px;
        }}
        ul {{
            background: #fff;
            padding: 20px 40px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            list-style-type: none;
        }}
        li {{
            margin-bottom: 10px;
            font-size: 1.1em;
        }}
        .table-container {{
            overflow-x: auto;
            background: #fff;
            padding: 10px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            margin-top: 20px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9em;
        }}
        th, td {{
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #3498db;
            color: white;
            position: sticky;
            top: 0;
        }}
        tr:hover {{
            background-color: #f5f5f5;
        }}
        tr:nth-child(even) {{
            background-color: #fafafa;
        }}
        code {{
            background-color: #f8f8f8;
            border: 1px solid #ddd;
            border-radius: 3px;
            padding: 2px 4px;
            font-family: 'Courier New', Courier, monospace;
            display: block;
            white-space: pre-wrap;
            word-break: break-all;
            max-width: 400px;
            max-height: 100px;
            overflow-y: auto;
        }}
        .status-pass {{
            color: #27ae60;
            font-weight: bold;
        }}
        .status-fail {{
            color: #e74c3c;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    {content}
</body>
</html>
"""
    
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_template)

if __name__ == "__main__":
    md_file = r'eval\evaluation_report_hybrid.md'
    html_file = r'report\evaluation_report.html'
    
    if not os.path.exists('report'):
        os.makedirs('report')
        
    md_to_html(md_file, html_file)
    print(f"Báo cáo đã được tạo tại: {{html_file}}")
