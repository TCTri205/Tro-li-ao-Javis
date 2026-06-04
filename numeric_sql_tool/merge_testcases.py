import pandas as pd
import os

def load_csv_safely(path, has_header=True):
    try:
        if has_header:
            return pd.read_csv(path)
        else:
            # For the advanced file which may not have a header
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

def main():
    # File paths
    file_basic = "eval/numeric_sql_testcases_ja.csv"
    file_advanced = "eval/new_100_advanced_testcases.csv"
    file_stress = "eval/stress_100_testcases_ja.csv"
    
    output_200 = "eval/combined_200_testcases_ja.csv"
    output_300 = "eval/combined_300_testcases_ja.csv"

    print("Step 1: Merging basic (100) and advanced (100) test cases...")
    df_basic = load_csv_safely(file_basic, has_header=True)
    df_basic.columns = [c.lower() for c in df_basic.columns]
    
    df_advanced = load_csv_safely(file_advanced, has_header=False)
    df_advanced.columns = [c.lower() for c in df_advanced.columns]
    
    combined_200_df = pd.concat([df_basic[['question', 'sql']], df_advanced[['question', 'sql']]], ignore_index=True)
    combined_200_df.to_csv(output_200, index=False, encoding='utf-8')
    print(f"Successfully merged {len(combined_200_df)} test cases into {output_200}")

    print("\nStep 2: Merging 200 combined with 100 stress test cases...")
    df_stress = load_csv_safely(file_stress, has_header=True)
    df_stress.columns = [c.lower() for c in df_stress.columns]
    
    combined_300_df = pd.concat([combined_200_df[['question', 'sql']], df_stress[['question', 'sql']]], ignore_index=True)
    combined_300_df.to_csv(output_300, index=False, encoding='utf-8')
    print(f"Successfully merged {len(combined_300_df)} test cases into {output_300}")

if __name__ == "__main__":
    main()
