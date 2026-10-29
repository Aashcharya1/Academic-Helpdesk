import csv, hashlib, json, statistics, threading, time, uuid, math
from datetime import datetime,timezone
from pathlib import Path
import psutil, requests, yaml
from .config import ROOT,CONFIG
from .importers import snapshot
from .service import HelpdeskService

def evaluate(dataset,matrix_path,questions_path,limit=None,resume=None):
    matrix=yaml.safe_load(Path(matrix_path).read_text())
    questions=[json.loads(l) for l in Path(questions_path).read_text(encoding='utf-8').splitlines() if l.strip()]
    if len(questions)!=30: raise ValueError('Freeze exactly 30 questions before evaluation')
    active=snapshot(dataset)
    if not active: raise ValueError('No active approved corpus')
    out=ROOT/'evaluation/results'/dataset;out.mkdir(parents=True,exist_ok=True)
    stamp=Path(resume).stem if resume else datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    results_file=Path(resume).resolve() if resume else out/f'{stamp}.jsonl'
    if not results_file.is_relative_to(out.resolve()):raise ValueError('Resume file must belong to the selected dataset results directory')
    tags=requests.get(CONFIG['ollama_url']+'/api/tags',timeout=10).json()
    code=hashlib.sha256()
    for folder in ('helpdesk','app'):
        for source in sorted((ROOT/folder).rglob('*.py')):code.update(str(source.relative_to(ROOT)).encode()+source.read_bytes())
    provenance={'matrix':matrix,'settings':CONFIG,'models':tags,'snapshot':str(active),'implementation_sha256':code.hexdigest(),'requirements_sha256':hashlib.sha256((ROOT/'requirements.lock').read_bytes()).hexdigest(),'questions_sha256':hashlib.sha256(Path(questions_path).read_bytes()).hexdigest(),'index':json.loads((active/'index.json').read_text()),'limitations':['Seed is requested through ADK; deterministic reproducibility is not guaranteed by Ollama/GPU.','Semantic groundedness, accuracy and citation support require human scoring.','Peak system RAM includes other running applications.']}
    provenance_file=out/f'{stamp}.provenance.json'
    if resume:
        previous=json.loads(provenance_file.read_text())
        if any(previous.get(key)!=provenance[key] for key in ('questions_sha256','index','matrix','settings','implementation_sha256','requirements_sha256')):raise ValueError('Cannot resume after questions, index, implementation, dependencies or settings changed')
    else:provenance_file.write_text(json.dumps(provenance,indent=2),encoding='utf-8')
    runs=[json.loads(l) for l in results_file.read_text(encoding='utf-8').splitlines()] if resume else []
    completed={(r['model'],r['mode'],r['seed'],r['id']) for r in runs}
    available_digests={m['name']:m['digest'] for m in tags.get('models',[])}
    if any(available_digests.get(r['model'])!=r['model_digest'] for r in runs):raise ValueError('Cannot resume after an executed chat model changed or became unavailable')
    (out/f'{stamp}.models.json').write_text(json.dumps(tags,indent=2),encoding='utf-8')
    stop=False;peak=0
    def monitor():
        nonlocal peak
        while not stop:
            peak=max(peak,psutil.virtual_memory().used);time.sleep(.5)
    thread=threading.Thread(target=monitor,daemon=True);thread.start()
    try:
        for model in matrix['models']:
            for wait_attempt in range(360):
                available=requests.get(CONFIG['ollama_url']+'/api/tags',timeout=10).json()['models']
                current=next((m for m in available if m['name']==model),None)
                if current:break
                if wait_attempt%12==0:print(f'Waiting for requested model {model}; completed trials remain saved.',flush=True)
                time.sleep(5)
            else:raise RuntimeError(f'{model} is still unavailable; resume saved trials after download completes')
            for mode in matrix['modes']:
                for seed in matrix['seeds']:
                    for q in questions:
                        if (model,mode,seed,q['id']) in completed:continue
                        if limit is not None and len(runs)>=limit: break
                        peak=psutil.virtual_memory().used
                        context={'dataset':dataset,**q.get('context',{})}
                        trial_session=uuid.uuid4().hex
                        setup_responses=[]
                        for turn in q.get('setup_turns',[]):
                            setup_responses.append(HelpdeskService().answer(turn,context,mode,model,session_id=trial_session,seed=seed,capture_raw=True).model_dump())
                        residency=requests.get(CONFIG['ollama_url']+'/api/ps',timeout=10).json().get('models',[])
                        warm=any(item.get('name')==model for item in residency)
                        response=HelpdeskService().answer(q['question'],context,mode,model,session_id=trial_session,seed=seed,capture_raw=True).model_dump()
                        row={'id':q['id'],'model':model,'model_digest':current['digest'],'mode':mode,'seed':seed,'status':response['status'],'expected_status':q['expected_status'],'status_match':response['status']==q['expected_status'],'latency_s':response['metrics']['latency_s'],'peak_system_ram_bytes':peak,'human_scored':False,'response':response,'gold':q.get('gold',{}),'timing':'first-in-sequence (cold/warm not guaranteed)' if q['id']=='Q01' else 'warm sequence (residency not guaranteed)'}
                        row.update(category=q.get('category'),setup_responses=setup_responses,timing='model resident before request' if warm else 'model not resident before request')
                        gold_ids={e['id'] for e in q.get('gold',{}).get('evidence',[])}
                        retrieved={e['id'] for call in response['metrics'].get('retrieval_calls',[]) for e in call}
                        row['retrieval_gold_hits']=len(gold_ids & retrieved) if retrieved else None
                        row['retrieval_gold_total']=len(gold_ids) if retrieved else None
                        runs.append(row)
                        with results_file.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
                        (out/f'{stamp}.checkpoint.json').write_text(json.dumps({'state':'running','executed':len(runs),'not_run':360-len(runs),'snapshot':str(active),'human_scored':False},indent=2))
                        print(f'{len(runs)}/360 {model} {mode} {seed} {q["id"]}: {row["status"]}',flush=True)
                    if limit is not None and len(runs)>=limit: break
                if limit is not None and len(runs)>=limit: break
            requests.post(CONFIG['ollama_url']+'/api/generate',json={'model':model,'keep_alive':0},timeout=60)
            if limit is not None and len(runs)>=limit: break
    finally:
        stop=True;thread.join(timeout=2)
    groups={}
    for r in runs:groups.setdefault((r['model'],r['mode'],r['id']),[]).append(r)
    changed=[]
    for (model,mode,qid),group in groups.items():
        normalized={json.dumps({'status':r['status'],'citations':sorted(c['id'] for c in r['response']['citations']),'draft':r['response']['draft'],'answer':r['response']['answer']},sort_keys=True) for r in group}
        if len(normalized)>1:changed.append({'model':model,'mode':mode,'id':qid,'outputs':[r['response'] for r in group],'human_substantive_change_review':'pending'})
    (out/f'{stamp}.changed.json').write_text(json.dumps(changed,indent=2),encoding='utf-8')
    fields=['id','model','mode','seed','fully_correct','supported_claims','total_claims','supporting_citations','total_citations','cited_claims','email_success','retrieval_gold_hits','retrieval_gold_total','reviewer','notes']
    with (out/f'{stamp}.human-scoring.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows({k:r[k] for k in ('id','model','mode','seed')} for r in runs)
    summary={'executed':len(runs),'not_run':360-len(runs),'raw_results':str(results_file),'median_latency_s':statistics.median(r['latency_s'] for r in runs) if runs else None,'p95_latency_s':sorted(r['latency_s'] for r in runs)[max(0,int(len(runs)*.95)-1)] if runs else None,'status_matches':sum(r['status_match'] for r in runs),'error_trials':sum(r['status']=='error' for r in runs),'changed_output_groups':len(changed),'accuracy':None,'groundedness':None,'citation_precision':None,'citation_coverage':None,'note':'Unscored metrics are null, not zero. Status matching is not factual accuracy. Human gold validation and scoring pending.'}
    (out/f'{stamp}.summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    from .evaluation_metrics import summarize
    (out/f'{stamp}.metrics.json').write_text(json.dumps(summarize(runs,out/f'{stamp}.human-scoring.csv'),indent=2),encoding='utf-8')
    (out/f'{stamp}.checkpoint.json').write_text(json.dumps({'state':'complete' if len(runs)==360 else 'partial','executed':len(runs),'not_run':360-len(runs)},indent=2))
    return summary
