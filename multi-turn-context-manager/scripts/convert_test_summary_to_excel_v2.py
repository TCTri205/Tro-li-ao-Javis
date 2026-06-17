import pandas as pd
import os
import unicodedata

def get_visual_width(text):
    """Calculate the visual width of text, considering multi-byte characters."""
    width = 0
    for char in str(text):
        if unicodedata.east_asian_width(char) in ('W', 'F', 'A'):
            width += 2
        else:
            width += 1
    return width

def convert_csv_to_xlsx(csv_path, xlsx_path):
    print(f"Reading CSV from: {csv_path}")
    df = pd.read_csv(csv_path, encoding='utf-8')
    
    print(f"Writing Excel to: {xlsx_path}")
    with pd.ExcelWriter(xlsx_path, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Test Summary')
        worksheet = writer.sheets['Test Summary']
        
        for i, col in enumerate(df.columns):
            # Calculate max visual width in the column
            max_width = get_visual_width(col)
            for val in df[col]:
                max_width = max(max_width, get_visual_width(val))
            
            # Add some padding and limit max width
            adjusted_width = min(max_width + 2, 100)
            worksheet.column_dimensions[chr(65 + i)].width = adjusted_width

    print("Conversion completed successfully.")

if __name__ == "__main__":
    base_dir = r"d:\VJ\Tro-li-ao-Javis\multi-turn-context-manager"
    csv_file = os.path.join(base_dir, "reports", "tests", "test_summary.csv")
    xlsx_file = os.path.join(base_dir, "reports", "tests", "test_summary.xlsx")
    
    if os.path.exists(csv_file):
        convert_csv_to_xlsx(csv_file, xlsx_file)
    else:
        print(f"Error: CSV file not found at {csv_file}")
