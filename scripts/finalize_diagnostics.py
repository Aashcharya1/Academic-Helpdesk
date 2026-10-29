"""Label stopped development pilots without changing their raw trial records."""
import csv,json,shutil,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from helpdesk.evaluation_metrics import summarize

directory=ROOT/'evaluation/results/real'
history=ROOT/'.cache/evaluation-checkpoint-history';history.mkdir(parents=True,exist_ok=True)
fields=['id','model','mode','seed','fully_correct','supported_claims','total_claims','supporting_citations','total_citations','cited_claims','email_success','retrieval_gold_hits','retrieval_gold_total','reviewer','notes']
for path in sorted(directory.glob('*.jsonl')):
    checkpoint=path.with_suffix('.checkpoint.json')
    state=json.loads(checkpoint.read_text(encoding='utf-8')) if checkpoint.exists() else {}
    if state.get('state')!='running':continue
    # These are the specifically identified, stopped development runs, not a
    # generic way to relabel a live or final benchmark.
    if path.stem not in ('20261029T195043','20261029T195425'):continue
    rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    shutil.copyfile(checkpoint,history/checkpoint.name)
    state.update(state='aborted_diagnostic',previous_state='running',executed=len(rows),not_run=360-len(rows),updated_at_utc=datetime.now(timezone.utc).isoformat(),reason='Development pilot stopped during native GPU startup failures; implementation/settings subsequently changed. Not a final evaluation.')
    checkpoint.write_text(json.dumps(state,indent=2),encoding='utf-8')
    scoring=path.with_suffix('.human-scoring.csv')
    if not scoring.exists():
        with scoring.open('w',newline='',encoding='utf-8') as stream:
            writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
            writer.writerows({k:r[k] for k in ('id','model','mode','seed')} for r in rows)
    path.with_suffix('.metrics.json').write_text(json.dumps(summarize(rows,scoring),indent=2),encoding='utf-8')
    path.with_suffix('.changed.json').write_text(json.dumps({'scope':'Interrupted diagnostic pilot; repeated groups were not completed. No changed-answer conclusion is supported.','groups':[]},indent=2),encoding='utf-8')
    print(path.name,len(rows),'aborted diagnostic; raw rows preserved')
