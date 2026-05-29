import json
from pathlib import Path
import sys
sys.stdout.reconfigure(encoding='utf-8')

data = json.loads(Path('reports/eval_generated.json').read_text(encoding='utf-8'))
total = len(data)

sem_failures = [r for r in data if r.get('semantic_severity') == 'error']
print(f"=== Semantic Failures ({len(sem_failures)}/{total}) ===\n")
for r in sem_failures:
    print(f"[{r['id']:03d}] {r['query']}")
    print(f"  SQL: {r['sql']}")
    sem = r.get('semantic_diagnostics', {})
    for dim, msgs in sem.get('details', {}).items():
        for msg in msgs:
            print(f"  [{dim}] {msg}")
    print()

print("\n=== Security/Schema Issues ===")
for r in data:
    if not r['security_ok'] or not r['schema_ok']:
        print(f"[{r['id']:03d}] {r['query']}")
        if not r['security_ok']: print(f"  SECURITY: {r['security_error']}")
        if not r['schema_ok']:   print(f"  SCHEMA:   {r['schema_error']}")
