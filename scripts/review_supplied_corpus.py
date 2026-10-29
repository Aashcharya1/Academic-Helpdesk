"""Apply builder review to this supplied corpus; final human adjudication is separate.

Private visual transcription corrections are loaded from data/review_overrides.json.
No academic rules are embedded in implementation code.
"""
import csv,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from helpdesk.config import ROOT,CONFIG
from helpdesk.importers import snapshot,make_chunks,write_csv
p=snapshot('real',True)
rows=list(csv.DictReader((p/'manifest.csv').open(encoding='utf-8-sig')))
overrides=json.loads((ROOT/'data/review_overrides.json').read_text(encoding='utf-8'))
chunks=[];approved=[];metadata={}
for row in rows:
    if row['duplicate_of']:continue
    doc_id=row['doc_id'];path=p/'working'/f'{doc_id}.json'
    if not path.exists() or row['extraction'].startswith('error'):continue
    units=json.loads(path.read_text(encoding='utf-8'))
    for unit in units:
        if unit['locator'] in overrides.get(doc_id,{}):
            unit.setdefault('raw_ocr',unit['text'])
            unit['text']=overrides[doc_id][unit['locator']]
            unit['method']='ocr_english_transcription_visually_checked'
    path.write_text(json.dumps(units,ensure_ascii=False,indent=2),encoding='utf-8')
    chunks.extend(make_chunks(Path(row['source_path']),doc_id,row['version'],units))
    # Unidentified curriculum applicability and unreadable bilingual thesis scan
    # remain available for review, but cannot ground chat answers yet.
    if row['filename']=='Safari.pdf' or row['filename'].startswith('Circular_55'):
        row['review_status']='pending_applicability_or_bilingual_review';continue
    approved.append(doc_id)
    authority='IIT Jodhpur academic export supplied by user; identified from document content, not independently authenticated'
    meta={'authority':authority,'term':CONFIG['term'],'program':'','cohort':'','source_url':'','completeness':'partial_or_unconfirmed','reviewer':'Codex builder','human_review':'pending'}
    if doc_id=='Da7cc450da9':meta.update(effective_date='2024-01-11 circular date',supersedes_scope='Minor/specialization credit requirements only; no blanket supersession of other clauses')
    if row['filename'].startswith('Fwd Elective Course Offering'):meta['excluded_locators']=['p.4']
    row['review_status']='builder_reviewed';row['authority']=authority
    metadata[doc_id]=meta
(p/'chunks.json').write_text(json.dumps(chunks,ensure_ascii=False),encoding='utf-8')
review={'approved':approved,'metadata':metadata,'complete_departments':[],'note':'Builder review of supplied evidence. Final human applicability/gold adjudication pending. No department offering completeness or inferred code levels approved.'}
(p/'review.json').write_text(json.dumps(review,indent=2),encoding='utf-8')
write_csv(p/'manifest.csv',rows)
faculty=json.loads((p/'faculty.json').read_text(encoding='utf-8'))
faculty=[f for f in faculty if not f['record_id'].startswith('FC-REVIEW-')]
for contact in json.loads((ROOT/'data/contact_overrides.json').read_text(encoding='utf-8')):
    source=next(r for r in rows if contact['filename_contains'] in r['filename'])
    unit=next(u for u in json.loads((p/'working'/f'{source["doc_id"]}.json').read_text(encoding='utf-8')) if u['locator']==contact['locator'])
    if contact['email'] not in unit['text'] or contact['code'] not in unit['text']:raise ValueError('Contact override lacks source support')
    faculty.append({k:v for k,v in contact.items() if k!='filename_contains'} | {'record_id':'FC-REVIEW-'+source['doc_id'],'source_doc_id':source['doc_id'],'version':source['version'],'term':CONFIG['term']})
(p/'faculty.json').write_text(json.dumps(faculty,indent=2),encoding='utf-8')
write_csv(p/'faculty.csv',faculty)
gaps=[
 {'pattern':'attendance','reason':'Current attendance policy and applicability of later examination amendments have not been confirmed; the older regulations alone are insufficient.','allow_draft':False},
 {'pattern':'make.?up|medical.leave.*(evidence|required)|evidence.*medical','reason':'The later applicable examination/medical-leave amendment is not supplied or verified. A request template can be drafted without asserting policy.','allow_draft':True},
 {'pattern':'(topics|syllabus|contents|content).*Autonomous Systems|Autonomous Systems.*(topics|syllabus|contents)','reason':'A current offering/timetable row is available, but a verified Autonomous Systems syllabus is not.','allow_draft':False},
 {'pattern':'(Humanities|Humanities electives|400.level).*(count|how many|offered|floated)|how many.*Humanities|those Humanities electives','reason':'Explicit level classification and completeness of the Humanities offering list have not been verified.','allow_draft':False},
 {'pattern':'(minimum|total|open elective).*credit.*(degree|cohort)|degree.*credit','reason':'Programme-specific curriculum/cohort applicability is unverified.','allow_draft':False}
]
(p/'gaps.json').write_text(json.dumps(gaps,indent=2),encoding='utf-8')
print(json.dumps({'snapshot':str(p),'approved':len(approved),'distinct':sum(not r['duplicate_of'] for r in rows),'chunks':len(chunks)},indent=2))
