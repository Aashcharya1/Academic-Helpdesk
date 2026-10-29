import hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
expected=json.loads((root/'data/audit/all_original_hashes.json').read_text(encoding='utf-8'))
failures=[]
for name,digest in expected.items():
    p=root/'data/private_import'/name
    if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:failures.append(name)
print(json.dumps({'originals_checked':len(expected),'unchanged':not failures,'failures':failures},indent=2))
if failures:raise SystemExit(1)
