"""Export the design's canonical CSV columns; unknown values remain blank."""
import sys,json,re,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from helpdesk.importers import snapshot,write_csv
from helpdesk.tools import normalize
p=snapshot('real',True)
records=json.loads((p/'records.json').read_text(encoding='utf-8'))
faculty=json.loads((p/'faculty.json').read_text(encoding='utf-8'))
slots=json.loads((p/'slots.json').read_text(encoding='utf-8'))
aliases={normalize(alias):f['name'] for f in faculty for alias in f.get('aliases',[f['name']])}
for f in faculty:f['instructor_id']='IN-'+hashlib.sha256(normalize(f['name']).encode()).hexdigest()[:12]
for r in records:
    names=[n.strip() for group in (r['instructor'],r.get('co_instructor','')) for n in re.split(r'\s+(?:and|&)\s+|\s*[/;]\s*',group) if n.strip() and n.strip()!='-']
    names=list(dict.fromkeys(aliases.get(normalize(n),n) for n in names))
    r['instructor_id']='|'.join('IN-'+hashlib.sha256(normalize(n).encode()).hexdigest()[:12] for n in names)
    r.setdefault('course_type',r.get('category',''));r.setdefault('elective_group','');r.setdefault('syllabus_ref','')
    r.setdefault('day','');r.setdefault('start','');r.setdefault('end','')
meetings=[]
for r in records:
    if r['kind']!='timetable':continue
    matched=[s for s in slots if s['slot'].strip()==r['slot'].strip()]
    if not matched:meetings.append(r);continue
    for s in matched:
        pieces=re.split(r'\s*[–-]\s*',s.get('time',''),maxsplit=1)
        meetings.append(r|{'record_id':r['record_id']+'-'+s['record_id'],'day':s['day'],'start':pieces[0] if len(pieces)==2 else '', 'end':pieces[1] if len(pieces)==2 else '', 'source_time':s.get('time',''),'meeting_source_record_id':s['record_id'],'meeting_source_doc_id':s['source_doc_id'],'meeting_locator':s['locator'],'time_interpretation':'Original clock text; AM/PM normalization unverified.'})
for name,rows in [('records',records),('faculty',faculty)]:
    (p/f'{name}.json').write_text(json.dumps(rows,indent=2),encoding='utf-8');write_csv(p/f'{name}.csv',rows)
for name,rows in [('courses',[r for r in records if r['kind']=='offering']),('offerings',[r for r in records if r['kind']=='offering']),('timetable',meetings)]:write_csv(p/f'{name}.csv',rows)
print(json.dumps({'courses':sum(r['kind']=='offering' for r in records),'timetable_meetings':len(meetings),'faculty_contacts':len(faculty)}))
