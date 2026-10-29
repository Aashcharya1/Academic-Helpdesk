"""Lossless source locators with conservative structured extraction."""
import csv, hashlib, json, re, shutil
from pathlib import Path
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from ..config import ROOT, dataset_dir, CONFIG

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def clean(text):
    text = text.replace('\x00', '').replace('\u200b','')
    redactions=ROOT/'data/redactions.json'
    if redactions.exists():
        for rule in json.loads(redactions.read_text(encoding='utf-8')):
            text=re.sub(rule['pattern'],rule['replacement'],text,flags=re.I)
    text=re.sub(r'\b[bBmM]\d{2}[A-Za-z]{2}\d{4}@[^\s>]+','[student email redacted]',text)
    return re.sub(r'[ \t]+',' ',text).strip()

def extract(path, ocr=True):
    path = Path(path)
    ext = path.suffix.lower()
    if ext == '.pdf':
        import pymupdf
        doc = pymupdf.open(path)
        engine = None
        for i, page in enumerate(doc):
            text = page.get_text(sort=True)
            method = 'text'
            if len(re.sub(r'\W','',text)) < 40 and ocr and page.get_images(full=True):
                import numpy as np
                from rapidocr import RapidOCR
                if engine is None:
                    engine = RapidOCR(params={'Global.model_root_dir':str(ROOT / '.cache/ocr')})
                pix = page.get_pixmap(matrix=pymupdf.Matrix(2,2),alpha=False)
                result = engine(np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,3))
                text = '\n'.join(result.txts or [])
                method = 'ocr_pending_review'
            yield {'locator':f'p.{i+1}', 'text':clean(text), 'method':method}
    elif ext == '.xlsx':
        from openpyxl import load_workbook
        from openpyxl.utils import get_column_letter
        wb = load_workbook(path,data_only=True)
        for sheet in wb:
            for n,row in enumerate(sheet.iter_rows(),1):
                cells = [f'{c.column_letter}{n}={c.value}' for c in row if c.value is not None]
                if cells:
                    yield {'locator':f"'{sheet.title}'!A{n}:{get_column_letter(sheet.max_column)}{n}", 'text':clean(' | '.join(cells)), 'method':'cells'}
    elif ext == '.docx':
        from docx import Document
        doc = Document(path)
        for n,p in enumerate(doc.paragraphs,1):
            if p.text.strip(): yield {'locator':f'paragraph {n}','text':clean(p.text),'method':'text'}
        for n,t in enumerate(doc.tables,1):
            for r,row in enumerate(t.rows,1):
                yield {'locator':f'table {n} row {r}','text':clean(' | '.join(c.text for c in row.cells)),'method':'table'}
    elif ext in ('.html','.htm'):
        from bs4 import BeautifulSoup
        yield {'locator':'body','text':clean(BeautifulSoup(path.read_text(encoding='utf-8'),'html.parser').get_text('\n')),'method':'text'}
    elif ext == '.eml':
        msg = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
        header = '\n'.join(f'{k}: {msg.get(k, "")}' for k in ('Subject','From','Date','Message-ID'))
        plain_found=False
        for n,part in enumerate(msg.walk()):
            if part.get_content_type() == 'text/plain' and part.get_content_disposition() != 'attachment':
                plain_found=True
                yield {'locator':f'message {msg.get("Message-ID", "unknown")} part {n}', 'text':clean(header+'\n'+part.get_content()),'method':'email'}
        if not plain_found:
            from bs4 import BeautifulSoup
            for n,part in enumerate(msg.walk()):
                if part.get_content_type()=='text/html' and part.get_content_disposition()!='attachment':
                    yield {'locator':f'message {msg.get("Message-ID", "unknown")} part {n}','text':clean(header+'\n'+BeautifulSoup(part.get_content(),'html.parser').get_text('\n')),'method':'email_html'}
    elif ext == '.csv':
        for n,row in enumerate(csv.reader(path.open(encoding='utf-8-sig')),1):
            yield {'locator':f'row {n}','text':clean(' | '.join(row)),'method':'table'}
    elif ext in ('.txt','.md'):
        yield {'locator':'text','text':clean(path.read_text(encoding='utf-8-sig')),'method':'text'}
    else:
        raise ValueError(f'Unsupported source type: {ext}')

def write_csv(path, rows, fields=None):
    if not fields: fields = list(dict.fromkeys(k for r in rows for k in r)) or ['record_id']
    with Path(path).open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(rows)

def make_chunks(path,doc_id,version,units):
    chunks=[]
    for unit in units:
        words=unit['text'].split()
        for start in range(0,len(words),290):
            text=' '.join(words[start:start+350])
            chunk_id=doc_id+'-'+hashlib.sha256((unit['locator']+str(start)+text).encode()).hexdigest()[:10]
            chunks.append({'id':chunk_id,'doc_id':doc_id,'version':version,'title':path.stem,'locator':unit['locator'],'text':text,'source_url':'','source_path':str(path.resolve()),'method':unit['method'],'term':CONFIG['term'],'program':'','cohort':''})
    return chunks

def structured(path, doc_id, version):
    from openpyxl import load_workbook
    from openpyxl.utils import get_column_letter
    records=[]; contacts=[]; slots=[]; mappings=[]
    wb=load_workbook(path,data_only=True)
    for s in wb:
        headers={}
        for ri,row in enumerate(s.iter_rows(values_only=True),1):
            vals=[str(v).strip() if v is not None else '' for v in row]
            norm=[re.sub(r'[^a-z]','',v.lower()) for v in vals]
            if any(x in ('coursecode','subjectcode','code') for x in norm):
                headers={i:v for i,v in enumerate(norm)}
                mappings.append({'sheet':s.title,'header_row':ri,'columns':{get_column_letter(i+1):vals[i] for i in headers if vals[i]}})
                continue
            locator=f"'{s.title}'!A{ri}:{get_column_letter(s.max_column)}{ri}"
            base={'source_doc_id':doc_id,'version':version,'locator':locator,'term':CONFIG['term']}
            # Contact tables: explicit name and email in same row, never guessed.
            emails=[v for v in vals if re.fullmatch(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',v,re.I)]
            if emails and ('Committee' in s.title):
                contacts.append({**base,'record_id':f'FC-{doc_id}-{s.title}-{ri}','name':vals[2], 'email':emails[0]})
            if s.title=='Slot System' and 3<=ri<=16 and vals[0]:
                for day,col in [('Mon',1),('Tue',3),('Wed',5),('Thu',7),('Fri',9)]:
                    for c in (col,col+1):
                        slot=vals[c].strip() if c<len(vals) else ''
                        if re.fullmatch(r'[A-Z]{1,3}\d?',slot):
                            slots.append({**base,'record_id':f'SL-{doc_id}-{ri}-{c}','slot':slot,'day':day,'time':vals[0]})
            if s.title=='Classroom Allocation':
                if re.fullmatch(r'[A-Z]{2,4}\d{4,5}',vals[0].replace(' ','')):
                    records.append({**base,'record_id':f'TT-{doc_id}-{ri}','code':vals[0].replace(' ',''),'title':vals[1],'ltp':vals[2],'credits':vals[3],'slot':vals[4],'department':vals[5],'instructor':vals[6],'co_instructor':vals[7],'venue':vals[9],'kind':'timetable','level':'','category':'','section':'','offered_status':'listed'})
                continue
            if not headers or 'Finalized' not in Path(path).name: continue
            data={headers[i]:v for i,v in enumerate(vals) if i in headers}
            def get(*keys): return next((data[k] for k in keys if data.get(k)), '')
            code=get('coursecode','subjectcode','code').replace(' ','').upper()
            if not re.fullmatch(r'[A-Z]{2,4}\d{4,5}',code): continue
            records.append({**base,'record_id':f'OF-{doc_id}-{s.title}-{ri}','code':code,'title':get('coursename','coursetitle','nameofthecourse','subjectname'),'ltp':get('ltp','ltpstructure','ltpcredits','creditltp'),'credits':get('credits','credit'),'slot':get('slot','preferredslot','preferredslots'),'department':s.title,'instructor':get('instructor','instructors','instructorname','nameof faculty'.replace(' ',''),'coursecoordinator','instructorcoordinator','instructorsreadascoordinator'),'co_instructor':get('coinstructors'),'venue':'','kind':'offering','level':get('level'),'category':get('category','coursetype','categorypcpeic','type'),'section':'','offered_status':'listed'})
    return records,contacts,slots,mappings

def ingest(dataset, input_dir, use_ocr=True):
    target=dataset_dir(dataset)
    candidate=target/'snapshots'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    candidate.mkdir(parents=True,exist_ok=False)
    manifest=[]; chunks=[]; seen={}; records=[]; contacts=[]; slots=[]; mappings=[]
    sources=[(p,'','') for p in sorted(Path(input_dir).iterdir())]
    for path,parent_id,message_id in sources:
        if not path.is_file() or path.suffix.lower() not in ('.pdf','.xlsx','.docx','.csv','.html','.htm','.eml','.txt','.md'): continue
        digest=sha(path); doc_id='D'+digest[:10]; version=digest[:12]
        item={'doc_id':doc_id,'title':path.stem,'filename':path.name,'sha256':digest,'version':version,'source_url':'','source_path':str(path.resolve()),'retrieval_date':CONFIG['snapshot_date'],'term':CONFIG['term'],'program':'','cohort':'','authority':'user-supplied academic export; review required','effective_date':'','supersedes':'','completeness':'unconfirmed','review_status':'pending','duplicate_of':seen.get(digest,'')}
        item.update(parent_doc_id=parent_id,message_id=message_id)
        manifest.append(item)
        if digest in seen: continue
        seen[digest]=doc_id
        try:
            if path.suffix.lower()=='.eml':
                msg=BytesParser(policy=policy.default).parsebytes(path.read_bytes())
                item['message_id']=str(msg.get('Message-ID',''))
                for attachment in msg.iter_attachments():
                    filename=Path(attachment.get_filename() or 'unnamed.bin').name
                    payload=attachment.get_payload(decode=True)
                    if not payload or Path(filename).suffix.lower() not in ('.pdf','.xlsx','.docx','.csv','.html','.txt','.eml'):continue
                    if len(payload)>200*1024*1024:raise ValueError('Attachment exceeds 200 MiB import limit')
                    destination=candidate/'attachments'/hashlib.sha256(payload).hexdigest()[:12]/filename
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    if not destination.exists():destination.write_bytes(payload)
                    sources.append((destination,doc_id,item['message_id']))
            units=list(extract(path,use_ocr))
            (candidate/'working').mkdir(exist_ok=True)
            (candidate/'working'/f'{doc_id}.json').write_text(json.dumps(units,ensure_ascii=False,indent=2),encoding='utf-8')
            chunks.extend(make_chunks(path,doc_id,version,units))
            if path.suffix.lower()=='.xlsx':
                r,c,s,m=structured(path,doc_id,version); records+=r; contacts+=c; slots+=s; mappings.append({'doc_id':doc_id,'mappings':m})
            item['extraction']='ocr_pending_review' if any(u['method']=='ocr_pending_review' for u in units) else 'extracted'
            item['chunks']=sum(c['doc_id']==doc_id for c in chunks)
        except Exception as e:
            item['extraction']='error: '+str(e)
    write_csv(candidate/'manifest.csv',manifest)
    for name,rows in [('records',records),('faculty',contacts),('slots',slots)]:
        (candidate/f'{name}.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
        write_csv(candidate/f'{name}.csv',rows)
    for name,rows in [('courses',[r for r in records if r['kind']=='offering']),('offerings',[r for r in records if r['kind']=='offering']),('timetable',[r for r in records if r['kind']=='timetable'])]: write_csv(candidate/f'{name}.csv',rows)
    (candidate/'chunks.json').write_text(json.dumps(chunks,ensure_ascii=False),encoding='utf-8')
    (candidate/'mappings.json').write_text(json.dumps(mappings,indent=2),encoding='utf-8')
    (candidate/'review.json').write_text(json.dumps({'approved':[],'metadata':{},'note':'Pending sources cannot answer real questions. Review extracted text, OCR and mappings before approval.'}),encoding='utf-8')
    (target/'candidate.txt').write_text(str(candidate),encoding='utf-8')
    return {'snapshot':str(candidate),'files':len(manifest),'distinct':len(seen),'chunks':len(chunks),'records':len(records)}

def snapshot(dataset, candidate=False):
    p=dataset_dir(dataset)/('candidate.txt' if candidate else 'active.txt')
    return Path(p.read_text(encoding='utf-8')) if p.exists() else None

def editable_candidate(dataset):
    """Keep review mutations away from the last successfully activated snapshot."""
    candidate=snapshot(dataset,True)
    if candidate is None or candidate!=snapshot(dataset):return candidate
    import shutil,uuid
    target=candidate.parent/(candidate.name+'-review-'+uuid.uuid4().hex[:8])
    shutil.copytree(candidate,target,ignore=shutil.ignore_patterns('chroma'))
    (dataset_dir(dataset)/'candidate.txt').write_text(str(target),encoding='utf-8')
    return target
