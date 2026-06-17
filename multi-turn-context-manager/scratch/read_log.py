import sys

log_file = r"C:\Users\This PC\.gemini\antigravity-cli\brain\1ad1350e-89ea-4e2d-9412-ecf5fcf0ca4e\.system_generated\tasks\task-112.log"
sys.stdout.reconfigure(encoding='utf-8')

with open(log_file, "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "NEG_017" in line:
        print(f"--- MATCH AT LINE {i+1} ---")
        for j in range(max(0, i-5), min(len(lines), i+30)):
            print(f"{j+1}: {lines[j].strip()}")
