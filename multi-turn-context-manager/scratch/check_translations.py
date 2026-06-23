import csv
import sys

csv_path = r"D:\VJ\Tro-li-ao-Javis\multi-turn-context-manager\reports\tests\test_summary_06_22.csv"
output_path = r"D:\VJ\Tro-li-ao-Javis\multi-turn-context-manager\scratch\full_translations.txt"

with open(csv_path, 'r', encoding='utf-8') as f:
    reader = csv.reader(f)
    rows = list(reader)

header = rows[0]
actual_idx = header.index("Actual Result (Captured Answer)")
translation_idx = header.index("Dịch Actual Result")

with open(output_path, 'w', encoding='utf-8') as out_f:
    for idx, row in enumerate(rows[1:], start=1):
        out_f.write(f"=== Row {idx} (Scenario: {row[2]}) ===\n")
        out_f.write(f"Original:\n{row[actual_idx]}\n")
        out_f.write(f"Translated:\n{row[translation_idx]}\n")
        out_f.write("\n" + "="*80 + "\n\n")

print("Done writing translations to file.")
