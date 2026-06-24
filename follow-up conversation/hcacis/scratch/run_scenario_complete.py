import subprocess
import os

env = os.environ.copy()
env['PYTHONIOENCODING'] = 'utf-8'

with open(r'd:\javis_text2sql\hcacis\output\kichban12_complete.txt', 'w', encoding='utf-8') as f:
    subprocess.run(
        [r'..\.venv\Scripts\python.exe', 'main.py', '-s', r'scenarios\scenario_complete.txt'],
        stdout=f,
        stderr=subprocess.STDOUT,
        env=env
    )
print("Done running scenario complete")
