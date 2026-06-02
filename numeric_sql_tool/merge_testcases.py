import pandas as pd
import io

def load_csv_safely(path, has_header=True):
    try:
        if has_header:
            return pd.read_csv(path)
        else:
            # For the advanced file which seemed to have issues and maybe no header
            # We'll read it manually to handle potential quoting/delimiter issues
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            data = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(',', 1)
                if len(parts) >= 2:
                    q = parts[0].strip()
                    sql = parts[1].strip()
                    if sql.endswith(','):
                        sql = sql[:-1].strip()
                    if sql.startswith('"') and sql.endswith('"'):
                        sql = sql[1:-1].strip()
                    sql = sql.replace('""', '"')
                    data.append({'question': q, 'sql': sql})
            return pd.DataFrame(data)
    except Exception as e:
        print(f"Error loading {path}: {e}")
        return pd.DataFrame()

# File paths
file1 = "eval/numeric_sql_testcases_ja.csv"
file2 = "eval/new_100_advanced_testcases.csv"
output_file = "eval/combined_200_testcases_ja.csv"

# Load files
df1 = load_csv_safely(file1, has_header=True)
# Rename columns to lowercase if needed
df1.columns = [c.lower() for c in df1.columns]

df2 = load_csv_safely(file2, has_header=False)

# Combine
combined_df = pd.concat([df1[['question', 'sql']], df2[['question', 'sql']]], ignore_index=True)

# Save
combined_df.to_csv(output_file, index=False, encoding='utf-8')
print(f"Successfully merged {len(combined_df)} test cases into {output_file}")
