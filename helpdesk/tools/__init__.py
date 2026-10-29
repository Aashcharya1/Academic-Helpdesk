import json, re, hashlib
from ..schemas import ToolResult, Evidence
from ..importers import snapshot

def normalize(s): return re.sub(r'[^a-z0-9]','',s.lower())

class DataTools:
    def __init__(self,dataset,context,retriever):
        self.context=context; self.retriever=retriever; self.path=snapshot(dataset)
        self.review=json.loads((self.path/'review.json').read_text()) if self.path else {'approved':[]}
        self.records=self.load('records'); self.faculty=self.load('faculty'); self.slots=self.load('slots')

    def load(self,name):
        if not self.path: return []
        return [r for r in json.loads((self.path/f'{name}.json').read_text(encoding='utf-8')) if r['source_doc_id'] in self.review['approved']]

    def evidence(self,row):
        c=next((c for c in self.retriever.chunks if c['doc_id']==row['source_doc_id'] and c['locator']==row['locator']),None)
        if not c: return None
        return Evidence(id=row['record_id'],doc_id=c['doc_id'],version=c['version'],title=c['title'],locator=c['locator'],text=c['text'],source_url=c['source_url'],source_path=c['source_path'])

    def resolve(self,ref):
        rows=[r for r in self.records if r['term']==self.context['term'] and (normalize(ref)==normalize(r['code']) or normalize(ref)==normalize(r['title']))]
        codes={r['code'] for r in rows}
        if len(codes)>1: return [],'ambiguous'
        return rows,'ok' if rows else 'not_found'

    def schedule(self,ref,section=''):
        section=section or self.context.get('section','')
        rows,status=self.resolve(ref)
        if status!='ok': return ToolResult(status=status,error_code='course_not_unique_or_missing')
        available_slots={r['slot'].strip().upper() for r in rows if r['slot'].strip() and r['slot'].strip().upper() not in ('TBD','TBA','-')}
        if len(available_slots)>1:
            return ToolResult(status='ambiguous',data=rows,evidence=[e for r in rows if (e:=self.evidence(r))],error_code='cross_source_slot_conflict')
        exact=[r for r in rows if r['kind']=='timetable']
        rows=exact or rows
        if section:
            rows=[r for r in rows if r.get('section')==section]
            if not rows: return ToolResult(status='incomplete',error_code='section_not_documented')
        facts={(r['slot'],r['venue'],r['instructor']) for r in rows}
        if len({r['slot'] for r in rows if r['slot']})>1:
            return ToolResult(status='ambiguous',data=rows,evidence=[e for r in rows if (e:=self.evidence(r))],error_code='conflicting_slots_or_sections')
        meetings=[s for s in self.slots if any(s['slot']==r['slot'].strip() for r in rows)]
        ev=[e for r in rows+meetings if (e:=self.evidence(r))]
        return ToolResult(status='ok',data={'courses':rows,'meetings':meetings,'note':'Slot times are provided only for exact slot matches; no inferred lab duration.'},evidence=ev)

    def instructor(self,ref,section=''):
        section=section or self.context.get('section','')
        rows,status=self.resolve(ref)
        if status!='ok':return ToolResult(status=status,error_code='course_not_unique_or_missing')
        if section:
            rows=[r for r in rows if r.get('section')==section]
            if not rows:return ToolResult(status='incomplete',error_code='section_not_documented')
        names=list(dict.fromkeys(n.strip() for r in rows for group in [r['instructor'],r.get('co_instructor','')] for n in re.split(r'\s+(?:and|&)\s+|\s*[/;]\s*',group) if n.strip() and n.strip()!='-'))
        alias_map={normalize(alias.removeprefix('Dr. ')):f['name'] for f in self.faculty for alias in f.get('aliases',[f['name']])}
        names=list(dict.fromkeys(alias_map.get(normalize(n.removeprefix('Dr. ')),n) for n in names))
        contacts=[f for f in self.faculty if any(normalize(f['name'].removeprefix('Dr. '))==normalize(n.removeprefix('Dr. ')) for n in names) or f.get('code') in {r['code'] for r in rows}]
        return ToolResult(status='ok' if contacts and len(names)==1 else 'incomplete',data={'instructors':names,'contacts':contacts,'recipient':contacts[0]['email'] if len(names)==1 and len(contacts)==1 else '[instructor email]','co_teacher_review':len(names)>1},evidence=[e for r in rows+contacts if (e:=self.evidence(r))],error_code='' if contacts and len(names)==1 else 'contact_missing_or_co_teacher_review')

    def count(self,department,level,category):
        if not any(r['kind']=='offering' and r['term']==self.context['term'] for r in self.records):return ToolResult(status='not_found',error_code='term_not_covered')
        rows=[r for r in self.records if r['kind']=='offering' and r['term']==self.context['term'] and normalize(department)==normalize(r['department'])]
        # Explicitly verified level/category/completeness are required; code digits are insufficient.
        complete=self.review.get('complete_departments',[])
        if department not in complete or any(not r['level'] or not r['category'] for r in rows):
            return ToolResult(status='incomplete',data={'reason':'Department completeness, explicit course levels or elective classification is unverified.','candidate_codes':sorted({r['code'] for r in rows})},error_code='count_not_supported')
        rows=[r for r in rows if str(r['level'])==str(level) and category.lower() in r['category'].lower()]
        return ToolResult(status='ok',data={'count':len({r['code'] for r in rows}),'courses':rows,'complete':True},evidence=[e for r in rows if (e:=self.evidence(r))])

    def compare(self,first,second):
        a=self.schedule(first);b=self.schedule(second)
        evidence=list({e.id:e for e in a.evidence+b.evidence}.values())
        if not evidence:return ToolResult(status='incomplete',error_code='source_provenance_unavailable')
        if a.status!='ok' or b.status!='ok':
            return ToolResult(status='incomplete',data={'first_status':a.status,'second_status':b.status},evidence=evidence,error_code='comparison_needs_two_unambiguous_courses')
        if not a.data['meetings'] or not b.data['meetings']:
            return ToolResult(status='incomplete',evidence=evidence,error_code='meeting_times_unavailable')
        def intervals(text):
            match=re.fullmatch(r'\s*(\d{1,2})(?::(\d{2}))?\s*[–-]\s*(\d{1,2})(?::(\d{2}))?\s*',text)
            if not match:return None
            h1,m1,h2,m2=(int(v or 0) for v in match.groups())
            if max(h1,h2)>23 or max(m1,m2)>59:return None
            if max(h1,h2)>12:
                start=h1*60+m1;end=h2*60+m2
                return [(start,end)] if end>start else None
            start=(h1%12)*60+m1;end=(h2%12)*60+m2
            if end<=start:end+=720
            return [(start,end),(start+720,end+720)]
        uncertain=False;overlap=False
        for x in a.data['meetings']:
            for y in b.data['meetings']:
                if x['day']!=y['day']:continue
                if x['record_id']==y['record_id']:overlap=True;continue
                ix,iy=intervals(x.get('time','')),intervals(y.get('time',''))
                if ix is None or iy is None:uncertain=True;continue
                possibilities=[max(s1,s2)<min(e1,e2) for s1,e1 in ix for s2,e2 in iy]
                if all(possibilities):overlap=True
                elif any(possibilities):uncertain=True
        if uncertain and not overlap:
            return ToolResult(status='incomplete',data={'reason':'Some source clock texts lack enough AM/PM information to determine overlap.'},evidence=evidence,error_code='clock_interpretation_ambiguous')
        text='The documented class meetings overlap.' if overlap else 'The documented class meetings do not overlap.'
        ids=sorted(e.id for e in evidence)
        computed=Evidence(id='CMP-'+hashlib.sha256('|'.join(ids).encode()).hexdigest()[:12],doc_id=evidence[0].doc_id,version=evidence[0].version,title='Derived schedule comparison',locator='Computed from '+', '.join(ids),text=text+' Computed by the backend from the cited course and exact slot rows; this comparison does not cover undocumented meetings.',source_path=evidence[0].source_path)
        return ToolResult(status='ok',data={'overlap':overlap,'answer':text,'coverage':'documented meetings only'},evidence=evidence+[computed])

def draft_email(kind,recipient,student_facts,dates):
    if recipient!='[instructor email]' and not re.fullmatch(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',recipient):
        raise ValueError('Invalid recipient')
    return {'recipient':recipient,'subject':f'Request: {kind}', 'body':f'Dear Professor,\n\nI am [student name], [roll number], enrolled in [course].\n\nI request {kind} for {dates or "[start date] to [end date]"}. {student_facts}\n\nPlease let me know the applicable process and any supporting information required.\n\nThank you,\n[student name]\n[roll number]','missing_fields':['Confirm student identity, course, dates, recipient and facts before use.'],'label':'Draft — review before use'}

def draft_academic_request(question,recipient,course):
    """Preserve the student's request when it is not a leave/makeup template."""
    draft=draft_email('academic request',recipient,'','')
    quiz=re.search(r'\bquiz\s*(\d+)\b',question,re.I)
    postponement=bool(re.search(r'postpon|reschedul',question,re.I))
    if postponement:
        assessment='Quiz '+quiz[1] if quiz else 'the assessment'
        subject=f'Request to postpone {assessment} — {course}'
        request=f'I would like to request a postponement of {assessment} for {course}. Please let me know whether rescheduling would be possible and which alternative date would be suitable.'
        # Preserve supplied reasons/dates verbatim rather than inventing them.
        detail=re.search(r'\b(?:because|due to|since)\s+(.+)',question,re.I)
        if detail:request+='\n\nReason provided: '+detail[1].strip()
        dates=re.findall(r'\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b',question)
        if dates:request+='\n\nRequested date details: '+', '.join(dates)+'.'
    else:
        subject=f'Academic request — {course}'
        request='I would appreciate your consideration of the following request:\n\n'+question.strip()
    draft.update(subject=subject,body=f'Dear Professor,\n\nI am [student name], [roll number], enrolled in {course}.\n\n{request}\n\nThank you for your consideration.\n\nRegards,\n[student name]\n[roll number]',missing_fields=['Confirm student identity, recipient and request details before use.'])
    return draft
