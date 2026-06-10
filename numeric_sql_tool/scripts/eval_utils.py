import re
import pandas as pd

def normalize_sql(sql: str) -> str:
    """Normalize a SQL query for strict semantic comparison:
    1. Convert to lowercase.
    2. Replace all whitespaces (spaces, tabs, newlines) with a single space.
    3. Remove whitespace around special operators/punctuation to ignore formatting differences.
    """
    if not sql or pd.isna(sql):
        return ""
    
    s = str(sql).strip().lower()
    
    # Check if it represents SKIP
    if "skip" in s:
        return "skip"
        
    s = s.replace("\n", " ").replace("\r", " ")
    # Unescape backslash-escaped characters (e.g. \| -> |)
    s = s.replace(r"\|", "|")
    
    # Replace multiple spaces with a single space
    s = " ".join(s.split())
    
    # Remove spacing around punctuation/operators: , ( ) = > < ! + - * / | : .
    # This aligns e.g. "t.id::text" and "t.id :: text", "sum(val), 0" and "sum(val),0"
    for char in [',', '(', ')', '=', '<', '>', '!', '+', '-', '*', '/', '|', ':', '.']:
        s = re.sub(rf'\s*\{char}\s*', char, s)
        
    # Strip trailing dummy parameters
    s = s.replace("and($5::text is null or true)", "")
    s = s.replace("and($6::text is null or true)", "")
    s = " ".join(s.split())
        
    return s.strip()

def is_semantically_match(sql_gt: str, sql_actual: str) -> bool:
    """Strict comparison of Ground Truth and Actual SQL after normalization."""
    norm_gt = normalize_sql(sql_gt)
    norm_actual = normalize_sql(sql_actual)
    
    if not norm_gt or not norm_actual:
        return norm_gt == norm_actual
        
    # If both are skips, they are semantically equal
    if norm_gt == "skip" and norm_actual == "skip":
        return True
        
    # If only one is skip, they are not equal
    if norm_gt == "skip" or norm_actual == "skip":
        return False
        
    return norm_gt == norm_actual
