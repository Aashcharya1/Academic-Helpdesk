"""Run the screenshot's prerequisite request through the actual local agent."""
import argparse,json,shutil,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from helpdesk.service import HelpdeskService,prerequisite_excerpt,prerequisite_evidence,normalized_quote
from helpdesk.schemas import Evidence

parser=argparse.ArgumentParser()
parser.add_argument('--model',required=True,choices=['qwen3:8b','llama3.1:8b'])
parser.add_argument('--mode',default='multi',choices=['single','multi'])
args=parser.parse_args()
question='What are the prerequisites for Computer-Aided Design?'
response=HelpdeskService().answer(question,{'dataset':'real'},args.mode,args.model,capture_raw=True).model_dump()
fields=[prerequisite_excerpt(e['text']) for e in response['citations'] if prerequisite_excerpt(e['text'])]
relevant=prerequisite_evidence([Evidence.model_validate(e) for e in response['citations']],question)
passed=response['status']=='answered' and bool(fields) and len(relevant)==len(response['citations']) and any(normalized_quote(field) in normalized_quote(response['answer']) for field in fields)
result={'model':args.model,'mode':args.mode,'passed':passed,'expected_fields_from_returned_sources':fields,'response':response,'executed_at_utc':datetime.now(timezone.utc).isoformat()}
destination=ROOT/'report/private'/f'course-regression-{args.model.replace(":","-")}-{args.mode}.json'
if destination.exists():
    history=destination.parent/'regression-history';history.mkdir(exist_ok=True)
    shutil.copyfile(destination,history/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+destination.name))
destination.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'model':args.model,'mode':args.mode,'passed':passed,'status':response['status'],'latency_s':response['metrics']['latency_s']},indent=2),flush=True)
if not passed:raise SystemExit(1)
