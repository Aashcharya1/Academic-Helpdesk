import json,time,shutil,hashlib
from datetime import datetime,timezone
from .config import ROOT
from .service import HelpdeskService

def smoke(model='qwen3:8b',mode='single',failed_only=False,recheck_cases=None):
    recheck_cases=set(recheck_cases or [])
    failed_only=failed_only or bool(recheck_cases)
    dest=ROOT/'report/private';dest.mkdir(parents=True,exist_ok=True)
    latest=dest/f'smoke-{model.replace(":","-")}-{mode}.json'
    history=dest/'smoke-history';history.mkdir(exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    previous={};previous_hash=None
    if latest.exists():
        shutil.copyfile(latest,history/f'{stamp}-previous-{latest.name}')
        if failed_only:
            previous_hash=hashlib.sha256(latest.read_bytes()).hexdigest()
            previous={row['case']:row for row in json.loads(latest.read_text(encoding='utf-8'))}
    cases=[
        ('schedule','Find the classroom and slot for DSL7410.','answered','lookup_course_schedule'),
        ('policy','What does Design Thinking teach about prototyping?','answered','search_documents'),
        ('email','Write an academic leave email to the instructor of DSL7220 for 2 days.','draft','create_email_draft'),
        ('compound','Find the slot for DSL7410 and draft a leave email for its instructor for 2 days.','draft','create_email_draft')]
    results=[];executed_now=[];reused_checks=[]
    for name,question,status,tool in cases:
        old=previous.get(name,{})
        if name not in recheck_cases and old.get('passed') and old.get('question')==question and old.get('model')==model and old.get('mode')==mode:
            row={**old,'reused_check':{'artifact_sha256':previous_hash,'reused_at_utc':stamp}}
            results.append(row);reused_checks.append(name)
            print(f'{model} {mode} {name}: prior passing check retained',flush=True)
            continue
        response=HelpdeskService().answer(question,{'dataset':'real'},mode,model,capture_raw=True).model_dump()
        called=[c['tool'] for c in response['metrics'].get('tool_trace',[])]
        passed=response['status']==status and tool in called
        if name=='compound':passed=passed and 'lookup_course_schedule' in called
        if name=='policy':passed=passed and any('Design Thinking' in e['title'] for e in response['citations'])
        row={'case':name,'question':question,'model':model,'mode':mode,'expected_status':status,'passed':passed,'response':response,'executed_at_utc':datetime.now(timezone.utc).isoformat()}
        executed_now.append(name)
        results.append(row)
        latest.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        (history/f'{stamp}-{latest.name}').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f'{model} {mode} {name}: {response["status"]}, tools={called}, passed={passed}',flush=True)
    latest.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    (history/f'{stamp}-{latest.name}').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    summary={'model':model,'mode':mode,'passed':len(results)==len(cases) and all(r['passed'] for r in results),'cases':len(results),'failed_cases':[r['case'] for r in results if not r['passed']],'executed_now':executed_now,'reused_checks':reused_checks}
    ready_file=ROOT/'.cache/runtime-ready.json'
    ready=json.loads(ready_file.read_text(encoding='utf-8')) if ready_file.exists() else {}
    ready[f'{model}/{mode}']=summary
    pending=ready_file.with_suffix('.tmp');pending.write_text(json.dumps(ready,indent=2),encoding='utf-8');pending.replace(ready_file)
    return summary
