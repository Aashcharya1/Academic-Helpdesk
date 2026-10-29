"""Print extraction diagnostics without treating availability as approval."""
import sys,json,csv
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from helpdesk.importers import snapshot
p=snapshot('real',True)
manifest=list(csv.DictReader((p/'manifest.csv').open(encoding='utf-8-sig')))
print(json.dumps({'snapshot':str(p),'manifest':manifest},indent=2,ensure_ascii=False))
records=json.loads((p/'records.json').read_text(encoding='utf-8'))
for ref in ('CSL7570','Autonomous Systems','DSL7560','AIL7260'):
    print(ref,json.dumps([r for r in records if ref.lower() in (r['code']+' '+r['title']).lower()],ensure_ascii=False,indent=2))
