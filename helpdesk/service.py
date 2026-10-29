import asyncio, json, re, threading, time, uuid, hashlib, unicodedata
from .config import CONFIG,ROOT
from filelock import FileLock
from .schemas import Context, Response, ToolResult
from .storage import log_unanswered, save_trace,load_session,save_session,redact
from .rag import Retriever
from .tools import DataTools, draft_email, normalize

MODEL_LOCK=threading.Lock()
PROCESS_LOCK=FileLock(str(ROOT/'.cache/inference.lock'),timeout=10)
UNKNOWN="I don't know from the available academic documents; this question has been logged for human review."
OOS="I don't know. This helpdesk only covers academic information and academic email drafts."

def parse_json(text):
    text=re.sub(r'<think>.*?</think>','',text,flags=re.S)
    start=text.find('{'); end=text.rfind('}')
    if start<0: raise ValueError('Model returned no structured response')
    obj=json.loads(text[start:end+1])
    for _ in range(3):
        if isinstance(obj,dict) and 'status' not in obj and isinstance(obj.get('result'),str) and obj['result'].strip():
            obj=parse_json(obj['result'])
        else:break
    return obj

def normalized_quote(text):
    return ' '.join(re.findall(r'\w+',unicodedata.normalize('NFKC',text).casefold()))

def prerequisite_excerpt(text):
    """Select an explicitly labelled field; never infer a prerequisite value."""
    match=re.search(r'\bpre[- ]?requisites?\b.*?(?=\b(?:Objectives?|Learning Outcomes?|Contents?|References?)\b|$)',text,re.I|re.S)
    return match.group().strip()[:600] if match else ''

def prerequisite_evidence(evidence,question,course=''):
    """Keep prerequisite fields tied to an explicitly named course/source."""
    query=normalize(question)
    codes=re.findall(r'\b[A-Z]{1,3}[LPTD]\s?\d{4,5}\b',question,re.I)
    if course:codes.append(course)
    return [e for e in evidence if prerequisite_excerpt(e.text) and (
        (len(normalize(e.title))>=6 and normalize(e.title) in query)
        or any(normalize(code) in normalize(e.text[:250]) for code in codes))]

def repair_quote_citations(obj,seen):
    """Repair a misplaced returned-source ID only when its quote has exact evidence.

    Invented IDs and fabricated quotes are never repaired. The raw model response
    remains in explicit evaluation captures; the UI displays only source quotes.
    """
    repaired=0
    for claim in obj.get('claims',[]):
        ids=claim.get('evidence_ids',[]);quote=claim.get('quote','').strip()
        if not ids or len(quote)<12 or any(i not in seen for i in ids):continue
        matches=[i for i,e in seen.items() if normalized_quote(quote) in normalized_quote(e.text)]
        if matches and any(i not in matches for i in ids):
            claim['evidence_ids']=matches[:2];repaired+=1
    return repaired

def validate_claims(obj,seen):
    claims=obj.get('claims',[])
    if not claims: return False
    for claim in claims:
        ids=claim.get('evidence_ids',[]); quote=claim.get('quote','').strip()
        if not ids or any(i not in seen for i in ids): return False
        if len(quote)<12 or not all(normalized_quote(quote) in normalized_quote(seen[i].text) for i in ids): return False
    return True

class HelpdeskService:
    def answer(self,question,context=None,mode='multi',model='qwen3:8b',session_id=None,seed=11,capture_raw=False):
        ctx=Context.model_validate(context or {}).model_dump()
        if mode not in ('single','multi') or model not in CONFIG['chat_models']: raise ValueError('Unapproved mode/model')
        request_id=uuid.uuid4().hex; start=time.monotonic(); seen={}; results=[]; draft=None
        session_id=session_id or request_id;session_key=None;topic=''
        metrics={'data_calls':0,'specialist_calls':0,'llm_calls':0}; intent='academic'; budget=None
        def finish(status,answer,citations=None,fields=None):
            if budget is not None:metrics.update(data_calls=budget.data,specialist_calls=budget.specialists,llm_calls=budget.llm,tool_trace=budget.calls,backend_finalizations=budget.backend_finalizations)
            metrics['latency_s']=round(time.monotonic()-start,3)
            response=Response(request_id=request_id,trace_id=request_id,status=status,answer=answer,citations=citations or [],draft=draft if status=='draft' else None,clarification_fields=fields or [],metrics=metrics)
            if status not in ('answered','draft'):
                log_unanswered(ctx['dataset'],request_id,question,ctx,intent,answer,list(seen),model,mode)
            elif metrics.get('unresolved_fields'):
                log_unanswered(ctx['dataset'],request_id,question,ctx,intent,'Partially completed; unavailable or ambiguous fields: '+', '.join(metrics['unresolved_fields']),list(seen),model,mode)
            save_trace(ctx['dataset'],request_id,{'status':status,'model':model,'mode':mode,'evidence_ids':list(seen),'metrics':{key:value for key,value in metrics.items() if key!='model_outputs'}})
            if session_key:
                save_session(ctx['dataset'],session_id,session_key,metrics.get('resolved_course',ctx.get('course','')),topic,list(seen))
            return response
        q=question.strip()
        if not q: return finish('needs_clarification','Please enter an academic question.',fields=['question'])
        email_intent=bool(re.search(r'draft|write.*(?:email|instructor)|request.*(?:leave|makeup)',q,re.I))
        schedule_intent=bool(re.search(r'slot|timetable|classroom|overlap|when.*meet',q,re.I))
        intent='mixed' if email_intent and schedule_intent else 'email' if email_intent else 'schedule' if schedule_intent else 'policy'
        academic=re.search(r'academic|course|exam|credit|attendance|instructor|semester|registration|elective|timetable|syllabus|leave|makeup|add.drop|withdraw|CSL|DSL|LAL|AIL|degree|policy|prerequisite|autonomous|teaches',q,re.I)
        unrelated=re.search(r'dining|weather|tourist|hostel|travel|city center|restaurant|best route|tell.*joke|write.*poem|cooking recipe',q,re.I)
        if unrelated and not academic:
            intent='out_of_scope'; return finish('out_of_scope',OOS)
        if re.search(r'degree|total credit|open elective credit|my.*curriculum',q,re.I) and (not ctx['program'] or not ctx['cohort']):
            missing_context=[key for key in ('program','cohort') if not ctx[key]]
            return finish('needs_clarification','Please confirm your exact programme/branch and admission cohort. A student name cannot establish programme applicability.',fields=missing_context)
        try:
            retriever=Retriever(ctx['dataset'],ctx)
            if not retriever.chunks: return finish('insufficient_evidence',UNKNOWN)
            gaps_file=retriever.path/'gaps.json'
            if gaps_file.exists():
                for gap in json.loads(gaps_file.read_text(encoding='utf-8')):
                    if re.search(gap['pattern'],q,re.I):
                        if gap.get('allow_draft') and re.search(r'draft|write|email|request a makeup',q,re.I): continue
                        return finish('insufficient_evidence',UNKNOWN+' '+gap['reason'])
            data=DataTools(ctx['dataset'],ctx,retriever)
            session_key=hashlib.sha256(json.dumps({'context':{key:value for key,value in ctx.items() if key!='course'},'mode':mode,'model':model,'index':(retriever.path/'index.json').read_text(encoding='utf-8')},sort_keys=True).encode()).hexdigest()
            previous=load_session(ctx['dataset'],session_id,session_key)
            if not ctx.get('course') and previous.get('course'):ctx['course']=previous['course']
            if previous.get('topic'):ctx['previous_topic']=previous['topic']
            if previous.get('evidence_ids'):ctx['previous_evidence_ids']=previous['evidence_ids'][:12]
            for pattern,label in [('add.?drop','course add/drop registration'),('withdraw','course withdrawal'),('registration','course registration'),('attendance','attendance policy'),('degree|total credit','degree credits'),('Humanities|electives','Humanities offerings'),('syllabus|topics|contents|prerequisite|prototyp','course contents and prerequisites'),('slot|timetable|classroom|meet','course schedule'),('leave|email|makeup','academic email request')]:
                if re.search(pattern,q,re.I):topic=label;break
            topic=topic or previous.get('topic','academic information')
            ctx['intent_topic']=topic
            refs=[r.replace(' ','').upper() for r in re.findall(r'\b[A-Z]{1,3}[LPTD]\s?\d{4,5}\b',q,re.I)]
            if refs and not re.search(r'draft|write.*email|write to|request.*leave|request.*makeup',q,re.I):
                missing=[ref for ref in refs if not any(ref==r['code'] for r in data.records) and not any(re.search(r'\b'+re.escape(ref)+r'\b',c['text'].replace(' ',''),re.I) for c in retriever.chunks)]
                if missing:return finish('insufficient_evidence',UNKNOWN+' No approved evidence was found for '+', '.join(missing)+'.')
            from .agents import Budget,execute
            budget=Budget()
            def capture(result):
                results.append(result)
                for e in result.evidence: seen[e.id]=e
                metrics['retrieved_ids']=list(seen)
                if result.error_code=='search':metrics.setdefault('retrieval_calls',[]).append([{'id':e.id,'score':e.retrieval_score} for e in result.evidence])
                payload=result.model_dump()
                # Full provenance remains in the backend; avoid repeating private paths
                # and metadata in the small local model's context window.
                payload['evidence']=[{'id':e.id,'title':e.title,'locator':e.locator,**({'text':e.text,'rrf_score':e.retrieval_score} if result.error_code=='search' else {})} for e in result.evidence]
                def compact(value):
                    if isinstance(value,list):return [compact(item) for item in value]
                    if isinstance(value,dict):return {key:compact(item) for key,item in value.items() if key not in ('source_path','source_doc_id','version','locator','term','cohort','program','aliases')}
                    return value
                payload['data']=compact(payload['data'])
                return payload
            def search_documents(question: str, k: int=4) -> dict:
                """Search approved applicable document evidence. At most two searches per request."""
                budget.check('data')
                if sum(r.error_code=='search' for r in results)>=2:
                    return capture(ToolResult(status='incomplete',data={'note':'The two-search limit was reached. Use only passages already returned, or abstain.'},error_code='search_limit'))
                # Local models sometimes encode an integer tool argument as a
                # JSON string. Normalize it before enforcing the retrieval cap.
                try:limit=int(k)
                except (TypeError,ValueError,OverflowError):limit=4
                # Preserve the student's entities and requested field. A child
                # agent's paraphrase can drop a course title or change intent.
                # Only the optional second search uses its reformulation.
                first_search=not any(r.error_code=='search' for r in results)
                search_query=q if first_search else q+'\nSearch phrasing: '+question
                ev=retriever.search(search_query,max(1,min(limit,4)))
                asks_prerequisite=bool(re.search(r'\bpre[- ]?requisites?\b',q,re.I))
                if asks_prerequisite:
                    ev=prerequisite_evidence(ev,q,ctx.get('course',''))
                payload=capture(ToolResult(status='ok' if ev else 'not_found',data={'note':'Candidate evidence; verify applicability, exceptions and exact claim support.'},evidence=ev,error_code='search'))
                if asks_prerequisite:
                    payload['data']['note']='Answer the requested prerequisite field. Quote its complete explicit value; unrelated objectives or timetable rows do not answer this request.'
                    for evidence in payload['evidence']:
                        if excerpt:=prerequisite_excerpt(evidence['text']):evidence['text']=excerpt
                return payload
            def lookup_course_schedule(course_ref: str, section: str='') -> dict:
                """Resolve exact code or full title and return verified timetable rows and slot times."""
                # A model must not invent a section filter that hides valid records.
                selected_section=ctx.get('section','') or (section if section and re.search(r'\bsection\s+'+re.escape(section)+r'\b',q,re.I) else '')
                budget.check('data'); result=data.schedule(course_ref,selected_section)
                if result.status=='ok' and result.data['courses']:metrics['resolved_course']=result.data['courses'][0]['code']
                if result.status=='ok' and isinstance(result.data,dict):
                    rows=result.data.get('courses',[])
                    if re.search(r'classroom|venue|\broom\b',q,re.I) and rows and not any(row.get('venue') for row in rows):metrics.setdefault('unresolved_fields',[]).append('classroom')
                    if re.search(r'\bslot\b',q,re.I) and rows and not any(row.get('slot') for row in rows):metrics.setdefault('unresolved_fields',[]).append('slot')
                return capture(result)
            def lookup_instructor(code: str, section: str='') -> dict:
                """Find instructors and explicit documented email contacts, or an unknown placeholder."""
                selected_section=ctx.get('section','') or (section if section and re.search(r'\bsection\s+'+re.escape(section)+r'\b',q,re.I) else '')
                budget.check('data'); return capture(data.instructor(code,selected_section))
            def compare_course_schedules(first_course: str, second_course: str) -> dict:
                """Determine overlap using both documented class schedules; refuse ambiguous clock interpretation."""
                budget.check('data');return capture(data.compare(first_course,second_course))
            def count_offerings(department: str, level: str, category: str='elective') -> dict:
                """Count distinct offered codes only when completeness and explicit level are verified."""
                budget.check('data'); return capture(data.count(department,level,category))
            def create_email_draft(kind: str, course_ref: str, student_facts: str='', dates: str='') -> dict:
                """Create editable academic email only. Use facts supplied by the student; never send."""
                nonlocal draft
                budget.check('data')
                if len(refs)==1:course_ref=refs[0]
                contact=data.instructor(course_ref)
                capture(contact)
                recipient=contact.data.get('recipient','[instructor email]') if isinstance(contact.data,dict) else '[instructor email]'
                # Model-generated tool arguments cannot introduce student facts.
                facts=student_facts if student_facts and student_facts.lower() in q.lower() else ''
                supplied_dates=dates if dates and dates.lower() in q.lower() and re.search(r'\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-z]+\s+\d{4}',dates) else ''
                if not facts:
                    reason=re.search(r'after missing (?:it|the exam|the examination) due to ([^.!?]+)',q,re.I)
                    if reason:facts='I missed the examination due to '+reason[1].strip()+'.'
                allowed_kind='makeup examination' if re.search(r'makeup|make.up',q,re.I) else ('sick leave' if re.search(r'\bsick leave\b',q,re.I) else 'leave')
                dates_match=re.search(r'\bfrom\s+(\d{1,2}\s+\w+\s+\d{4})\s+to\s+(\d{1,2}\s+\w+\s+\d{4})\b',q,re.I)
                if dates_match:
                    from datetime import datetime
                    try:
                        begin=datetime.strptime(dates_match[1],'%d %B %Y');end=datetime.strptime(dates_match[2],'%d %B %Y')
                        if end>=begin:supplied_dates=dates_match[1]+' to '+dates_match[2]
                    except ValueError:pass
                draft=draft_email(allowed_kind,recipient,facts,supplied_dates)
                draft['body']=draft['body'].replace('[course]',course_ref)
                duration=re.search(r'\b(\d+)\s+days?\b',q,re.I)
                if duration and not re.search(r'\b'+duration[1]+r'\s+days?\b',draft['body'],re.I):draft['body']=draft['body'].replace('Please let me know',f'The requested duration is {duration[1]} day(s).\n\nPlease let me know')
                draft['contact_status']=contact.status
                if contact.status!='ok':metrics.setdefault('unresolved_fields',[]).append('recipient')
                draft['co_teacher_review']=bool(isinstance(contact.data,dict) and contact.data.get('co_teacher_review'))
                if draft['co_teacher_review']:draft['missing_fields'].append('Multiple instructors are listed. Confirm the intended recipient(s).')
                return {'status':'ok','data':draft,'evidence_ids':[e.id for e in contact.evidence]}
            tools={f.__name__:f for f in (search_documents,lookup_course_schedule,lookup_instructor,compare_course_schedules,count_offerings,create_email_draft)}
            async def run():
                return await asyncio.wait_for(execute(q,ctx,mode,model,tools,budget,request_id,seed),timeout=CONFIG['request_timeout'])
            with MODEL_LOCK,PROCESS_LOCK:
                import requests
                residents=requests.get(CONFIG['ollama_url']+'/api/ps',timeout=10)
                residents.raise_for_status()
                for resident in residents.json().get('models',[]):
                    name=resident.get('name','')
                    if name in CONFIG['chat_models'] and name!=model:
                        unloaded=requests.post(CONFIG['ollama_url']+'/api/generate',json={'model':name,'keep_alive':0},timeout=60)
                        unloaded.raise_for_status()
                raw=asyncio.run(run())
            if capture_raw:metrics['model_outputs']=[raw]
            metrics.update({'data_calls':budget.data,'specialist_calls':budget.specialists,'llm_calls':budget.llm,'tool_trace':budget.calls,'snapshot':str(retriever.path)})
            try:obj=parse_json(raw)
            except (ValueError,json.JSONDecodeError):
                # The tool-created draft is already typed and grounded. A malformed
                # model summary must not discard a successful draft.
                if draft:obj={'status':'draft'}
                elif any(r.status=='ok' and isinstance(r.data,dict) and ('meetings' in r.data or 'overlap' in r.data or 'count' in r.data) for r in results) and not any(r.error_code=='search' for r in results):obj={'status':'answered'}
                else:
                    obj=None
            if obj is None:
                if budget.llm>=CONFIG['max_llm_calls']-1:raise ValueError('Model returned invalid JSON within generation limit')
                async def repair_json():
                    return await asyncio.wait_for(execute(q+'\nReturn one valid concise JSON object. At most two short claims; do not truncate JSON. Use tools for evidence or abstain.',ctx,mode,model,tools,budget,request_id+'-json-repair',seed),timeout=max(1,CONFIG['request_timeout']-(time.monotonic()-start)))
                with MODEL_LOCK,PROCESS_LOCK:repaired=asyncio.run(repair_json())
                if capture_raw:metrics['model_outputs'].append(repaired)
                metrics['repair_attempted']=True
                obj=parse_json(repaired)
            status=obj.get('status','insufficient_evidence')
            status={'ok':'answered','ambiguous':'needs_clarification','incomplete':'insufficient_evidence','not_found':'insufficient_evidence'}.get(status,status)
            wants_draft=bool(re.search(r'draft|write.*(?:email|instructor)|request.*(?:leave|makeup)',q,re.I))
            if ((not budget.data and status in ('insufficient_evidence','needs_clarification')) or (wants_draft and draft is None)) and not metrics.get('repair_attempted'):
                async def retrieve_repair():
                    instruction=('The requested draft is missing. Call create_email_draft now (email_agent in multiagent mode), preserving the exact requested course. Missing contacts use placeholders. Do not repeat schedule lookups already completed.' if wants_draft else 'You have not checked the corpus yet. Call the appropriate data tool (or specialist in multiagent mode) now. For course contents, call search_documents through policy_agent. Return evidence-based JSON.')
                    return await asyncio.wait_for(execute(q+'\n'+instruction,ctx,mode,model,tools,budget,request_id+'-retrieval-repair',seed),timeout=max(1,CONFIG['request_timeout']-(time.monotonic()-start)))
                with MODEL_LOCK,PROCESS_LOCK:repaired=asyncio.run(retrieve_repair())
                if capture_raw:metrics['model_outputs'].append(repaired)
                metrics['repair_attempted']=True
                obj={'status':'draft'} if draft else parse_json(repaired);status=obj.get('status','insufficient_evidence')
            if status=='out_of_scope':return finish('out_of_scope',OOS)
            if draft:
                answer='Draft — review before use. Confirm all placeholders and recipient. No email has been sent.'
                schedules=[r for r in results if r.status=='ok' and isinstance(r.data,dict) and 'courses' in r.data]
                for result in schedules:
                    for row in result.data['courses']:
                        ref=next((e.id for e in result.evidence if e.id==row['record_id']),'')
                        answer+=f'\n\n{row["code"]}: slot {row["slot"] or "not documented"}; venue {row["venue"] or "not documented"}. [{ref}]'
                    if result.data['meetings']:
                        answer+='\nDocumented meetings: '+', '.join(f'{r["day"]} {r["time"]}' for r in result.data['meetings'])+'.'
                if re.search(r'\b(slot|timetable|classroom|schedule)\b',q,re.I) and not schedules:
                    answer+='\n\nThe schedule part was not verified and has been logged for review.'
                    log_unanswered(ctx['dataset'],request_id,q,ctx,'mixed','compound_schedule_part_unresolved',list(seen),model,mode)
                return finish('draft',answer,list(seen.values()))
            if status=='needs_clarification' or any(r.status=='ambiguous' for r in results):
                fields=[f for f in obj.get('clarification_fields',[]) if f in ('program','cohort','course','section','dates','recipient','source_precedence')]
                return finish('needs_clarification','Please confirm the course, section or applicable source update. The available records do not establish one unambiguous answer.',list(seen.values()),fields=fields or ['course','section','source_precedence'])
            structured=[];structured_ids=[]
            for result in results:
                if result.status!='ok' or not isinstance(result.data,dict) or result.error_code=='search':continue
                values=result.data
                refs=' '.join(f'[{e.id}]' for e in result.evidence)
                if 'meetings' in values and 'courses' in values:
                    for row in values['courses']:
                        structured.append(f'{row["code"]} — {row["title"]}: slot {row["slot"] or "not documented"}; classroom {row["venue"] or "not documented"}. [{row["record_id"]}]')
                    for meeting in values['meetings']:
                        structured.append(f'{meeting["day"]}: {meeting["time"]} (source clock format). [{meeting["record_id"]}]')
                elif 'overlap' in values:
                    structured.append(values['answer']+' Coverage: documented meetings only. '+refs)
                elif 'count' in values and values.get('complete'):
                    structured.append(f'{values["count"]} distinct offered courses: '+', '.join(f'{r["code"]} — {r["title"]}' for r in values['courses'])+'. '+refs)
                elif 'instructors' in values:
                    structured.append('Instructor(s): '+', '.join(values['instructors'])+'. Documented contact: '+values['recipient']+'. '+refs)
                else:continue
                structured_ids.extend(e.id for e in result.evidence)
            if structured and not wants_draft and not any(r.error_code=='search' for r in results):
                return finish('answered','\n\n'.join(dict.fromkeys(structured)),[seen[i] for i in dict.fromkeys(structured_ids)])
            if status=='answered':metrics['citation_pointer_repairs']=repair_quote_citations(obj,seen)
            def supported_answer(obj):
                if not validate_claims(obj,seen):return False
                if re.search(r'\bpre[- ]?requisites?\b',q,re.I):
                    return any(re.search(r'\bpre[- ]?requisites?\b',claim.get('quote',''),re.I) for claim in obj.get('claims',[]))
                return True
            if status=='answered' and not supported_answer(obj) and not metrics.get('repair_attempted') and budget.llm<CONFIG['max_llm_calls']-1:
                # One bounded repair; same per-request counters and evidence map.
                async def repair():
                    return await asyncio.wait_for(execute(q+'\nYour previous answer failed evidence validation. Use tools and return only exact supporting quotes with returned evidence IDs, or abstain.',ctx,mode,model,tools,budget,request_id+'-repair',seed),timeout=max(1,CONFIG['request_timeout']-(time.monotonic()-start)))
                with MODEL_LOCK,PROCESS_LOCK:repaired=asyncio.run(repair())
                if capture_raw:metrics['model_outputs'].append(repaired)
                obj=parse_json(repaired)
                status=obj.get('status','insufficient_evidence')
                metrics['repair_attempted']=True
            if status!='answered' or not supported_answer(obj):
                return finish('insufficient_evidence',UNKNOWN)
            # Render exact copied evidence, rather than unverified model paraphrases. Semantic
            # relevance remains a separately human-scored evaluation dimension.
            ids=list(dict.fromkeys(i for c in obj['claims'] for i in c['evidence_ids']))
            lines=[]
            for claim in obj['claims']:
                cite=' '.join(f'[{i}]' for i in claim['evidence_ids'])
                lines.append(f'{claim["quote"].strip()} {cite}')
            answer='\n\n'.join(lines)
            if unrelated: answer+='\n\nThe nonacademic part is outside this helpdesk’s scope.'
            return finish('answered',answer,[seen[i] for i in ids])
        except Exception as e:
            metrics['error_type']=type(e).__name__
            metrics['error_detail']=redact(str(e))[:1200]
            return finish('error','The local model service could not complete this request. Check model health and retry. The failure has been logged for review.')
