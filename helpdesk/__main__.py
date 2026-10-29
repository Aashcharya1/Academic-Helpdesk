import argparse,json,sys
if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
from .config import ROOT,dataset_dir

def main():
    parser=argparse.ArgumentParser(prog='helpdesk')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('doctor');p.add_argument('--inference',action='store_true')
    p=sub.add_parser('ingest');p.add_argument('--dataset',choices=['real','demo'],required=True);p.add_argument('--input',required=True);p.add_argument('--no-ocr',action='store_true')
    p=sub.add_parser('index');p.add_argument('--dataset',choices=['real','demo'],required=True)
    p=sub.add_parser('verify-data');p.add_argument('--dataset',choices=['real','demo'],default='real')
    p=sub.add_parser('smoke');p.add_argument('--model',default='qwen3:8b');p.add_argument('--mode',default='single',choices=['single','multi']);p.add_argument('--failed-only',action='store_true',help='Recheck failed cases and retain audited prior passing checks for this model/mode.');p.add_argument('--case',action='append',choices=['schedule','policy','email','compound'],help='Recheck this case plus any failed cases, retaining other audited passing checks.')
    p=sub.add_parser('ask');p.add_argument('question');p.add_argument('--dataset',default='real',choices=['real','demo']);p.add_argument('--mode',choices=['single','multi'],default='multi');p.add_argument('--model',default='qwen3:8b');p.add_argument('--program',default='')
    p=sub.add_parser('evaluate');p.add_argument('--dataset',choices=['real','demo'],required=True);p.add_argument('--matrix',default='evaluation/matrix.yaml');p.add_argument('--limit',type=int);p.add_argument('--questions',default='evaluation/questions.jsonl');p.add_argument('--resume')
    args=parser.parse_args()
    if args.command=='doctor':
        from .doctor import doctor
        result=doctor(args.inference)
        (ROOT/'report/private').mkdir(parents=True,exist_ok=True)
        (ROOT/'report/private/doctor.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    elif args.command=='ingest':
        from .importers import ingest
        result=ingest(args.dataset,args.input,not args.no_ocr)
    elif args.command=='index':
        from .importers import snapshot
        from .rag import build_index
        candidate=snapshot(args.dataset,True)
        result=build_index(candidate)
        (dataset_dir(args.dataset)/'active.txt').write_text(str(candidate),encoding='utf-8')
    elif args.command=='verify-data':
        from .validation import verify_data
        result=verify_data(args.dataset)
    elif args.command=='smoke':
        from .smoke import smoke
        result=smoke(args.model,args.mode,args.failed_only,args.case)
    elif args.command=='ask':
        from .service import HelpdeskService
        result=HelpdeskService().answer(args.question,{'dataset':args.dataset,'program':args.program},args.mode,args.model).model_dump()
    elif args.command=='evaluate':
        from .evaluation import evaluate
        result=evaluate(args.dataset,args.matrix,args.questions,args.limit,args.resume)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
