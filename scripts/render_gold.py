"""Readable view of frozen candidate gold; no new academic facts are generated."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
questions=[json.loads(line) for line in (ROOT/'evaluation/questions.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
lines=['# Candidate expected answers and source evidence','','Derived from the supplied private corpus. Human source/applicability adjudication is pending. This readable view does not change the frozen question file. Full source passages and records remain in questions.jsonl and the originals.','']
for row in questions:
    gold=row['gold']
    lines += [f'## {row["id"]}: {row["question"]}','',f'Expected decision: **{row["expected_status"]}**. Category: {row["category"]}.','']
    if row.get('setup_turns'):lines+=['Session setup: '+json.dumps(row['setup_turns'],ensure_ascii=False),'']
    if 'expected_answer' in gold:
        lines += ['Candidate expected answer:','', '```json',json.dumps(gold['expected_answer'],ensure_ascii=False,indent=2),'```','']
    for requirement in gold.get('requirements',[]):lines+=['- '+requirement]
    lines+=['']
    if gold.get('case_note'):lines+=[gold['case_note'],'']
    if gold.get('verification'):lines+=[gold['verification'],'']
    evidence=gold.get('evidence',[])
    if evidence:
        lines+=['Source candidates (excerpts below are shortened for navigation):','']
        for item in evidence:
            lines += [f'- `{item["id"]}` · {item["locator"]} · version {item["version"]}: '+item['quote'][:240].replace('\n',' ')+'…']
    if gold.get('exact_records'):
        lines+=['','Exact source records:','', '| Record | Code | Title | Slot | Locator |','|---|---|---|---|---|']
        for item in gold['exact_records']:
            lines.append('| '+' | '.join(str(item.get(key,'')).replace('|',' / ') for key in ('record_id','code','title','slot','locator'))+' |')
    lines+=['']
dest=ROOT/'report/private/GOLD.md';dest.parent.mkdir(exist_ok=True,parents=True)
dest.write_text('\n'.join(lines),encoding='utf-8')
print(dest)
