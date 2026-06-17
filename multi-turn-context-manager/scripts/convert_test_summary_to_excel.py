import pandas as pd
import os
import unicodedata

def get_visual_width(text):
    """
    Calculate the visual width of text, considering multi-byte characters 
    (Japanese, Vietnamese, etc.) for better Excel column auto-fitting.
    """
    width = 0
    for char in str(text):
        # 'W' (Wide), 'F' (Fullwidth), 'A' (Ambiguous) are treated as 2 units
        if unicodedata.east_asian_width(char) in ('W', 'F', 'A'):
            width += 2
        else:
            width += 1
    return width

def convert_csv_to_xlsx(csv_path, xlsx_path):
    print(f"Reading CSV from: {csv_path}")
    # Read the CSV with UTF-8 encoding
    try:
        df = pd.read_csv(csv_path, encoding='utf-8')
    except UnicodeDecodeError:
        # Fallback for other potential encodings if UTF-8 fails
        df = pd.read_csv(csv_path, encoding='shift_jis')
    
    print(f"Writing Excel to: {xlsx_path}")
    # Use openpyxl engine for advanced formatting
    with pd.ExcelWriter(xlsx_path, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Test Summary')
        worksheet = writer.sheets['Test Summary']
        
        # Auto-adjust column widths based on visual character width
        for i, col in enumerate(df.columns):
            # Start with column header width
            max_width = get_visual_width(col)
            
            # Check width of each cell in the column (sample first 100 rows for speed if file is huge)
            sample_df = df[col].head(100)
            for val in sample_df:
                max_width = max(max_width, get_visual_width(val))
            
            # Add padding and set limits (min 10, max 100)
            adjusted_width = max(10, min(max_width + 2, 100))
            
            # Convert index to Excel column letter (A, B, C...)
            column_letter = chr(65 + i) if i < 26 else f"{chr(64 + i // 26)}{chr(65 + i % 26)}"
            worksheet.column_dimensions[column_letter].width = adjusted_width

    print("Conversion completed successfully with visual width optimization.")

if __name__ == "__main__":
    # Use absolute paths or detect based on script location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.abspath(os.path.join(script_dir, ".."))
    
    csv_file = os.path.join(base_dir, "reports", "tests", "test_summary.csv")
    xlsx_file = os.path.join(base_dir, "reports", "tests", "test_summary.xlsx")
    
    if os.path.exists(csv_file):
        convert_csv_to_xlsx(csv_file, xlsx_file)
    else:
        print(f"Error: CSV file not found at {csv_file}")
