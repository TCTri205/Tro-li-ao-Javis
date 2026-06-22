import csv
import sys

sys.stdout.reconfigure(encoding='utf-8')

csv_path = r"D:\VJ\Tro-li-ao-Javis\multi-turn-context-manager\reports\tests\test_summary_06_22.csv"
with open(csv_path, 'r', encoding='utf-8') as f:
    reader = csv.reader(f)
    rows = list(reader)
    for idx, row in enumerate(rows):
        if 'V2_ENTITY_MEMORY' in row:
            print(f"Found at Row {idx}: {len(row)} columns")
            print(f"  Content: {row[0]}, {row[1]}, {row[2]}, {row[6]}")
            print(f"  Actual: {row[8][:150]}...")
