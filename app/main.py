import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import csv, json, uuid, hashlib, html
import pandas as pd
import requests
import streamlit as st
from helpdesk.config import CONFIG,dataset_dir
from helpdesk.importers import ingest,snapshot,write_csv,editable_candidate
from helpdesk.rag import build_index
from helpdesk.service import HelpdeskService
from helpdesk.storage import db
from helpdesk.health import is_ready

st.set_page_config(page_title='Academic Helpdesk',page_icon='◈',layout='wide',initial_sidebar_state='expanded')
st.markdown('<style>'+(ROOT/'app/styles.css').read_text(encoding='utf-8')+'</style>',unsafe_allow_html=True)
available_models=[];model_info={}
with st.sidebar:
    st.markdown('<div class="brand">Academic Helpdesk<small>IIT Jodhpur · Local workspace</small></div>',unsafe_allow_html=True)
    if st.button('New chat',use_container_width=True):
        st.session_state.messages=[];st.session_state.session_id=uuid.uuid4().hex
        st.session_state.pop('course',None)
        st.session_state.page='Chat'
    page=st.radio('Navigation',['Chat','Sources','Import & review','Review queue','Experiments'],key='page',label_visibility='collapsed')
    st.space('medium')
    with st.expander('Chat settings'):
        dataset=st.selectbox('Dataset',['real','demo'])
        mode=st.selectbox('Agent mode',['multi','single'],format_func=lambda x:'Multiagent specialists' if x=='multi' else 'Single-agent baseline')
        model=st.selectbox('Local model',CONFIG['chat_models'])
        term=st.text_input('Active term',CONFIG['term'])
        program=st.text_input('Programme and branch',CONFIG['program'],placeholder='Confirm exact programme')
        cohort=st.text_input('Admission cohort',CONFIG['cohort'])
        section=st.text_input('Course section (if applicable)')
    try:
        tags=requests.get(CONFIG['ollama_url']+'/api/tags',timeout=3).json()['models']
        available_models=[m['name'] for m in tags]
        model_info={m['name']:m for m in tags}
        st.caption('● Local runtime connected')
    except Exception:
        st.caption('○ Local runtime offline · Run Start.cmd')
    with st.expander('Model status'):
        for name in [*CONFIG['chat_models'],CONFIG['embedding_model']]:
            item=model_info.get(name,{})
            size=f" · {item['size']/1e9:.2f} GB" if item.get('size') else ''
            st.caption(name+(' · installed'+size if name in available_models else ' · not available'))
        st.caption('Chat runs locally on CPU.')
        if st.button('Refresh model status'):st.rerun()
    st.caption('Private documents · Drafts only')
    runtime_ready=is_ready(model,mode)

active=snapshot(dataset)
active_index_hash=hashlib.sha256((active/'index.json').read_bytes()).hexdigest() if active and (active/'index.json').exists() else ''
key=(dataset,mode,model,term,program,cohort,section,str(active),active_index_hash)
if st.session_state.get('context_key')!=key:
    st.session_state.context_key=key; st.session_state.messages=[]; st.session_state.session_id=uuid.uuid4().hex
    st.session_state.pop('course',None)
context=dict(dataset=dataset,term=term,program=program,cohort=cohort,section=section)
approved=len(json.loads((active/'review.json').read_text())['approved']) if active else 0
if page!='Chat':st.markdown('<style>.block-container{max-width:1200px}</style>',unsafe_allow_html=True)
if page=='Chat':
    if model not in available_models:st.info('This model is not available yet. Choose another in Chat settings.')
    elif not runtime_ready:st.info('Integration checks are running for this model and mode. Choose a validated profile in Chat settings.')
    suggestion=None
    if not st.session_state.messages:
        st.markdown('<div class="welcome"><h1>What can I help you with?</h1><p>Your academic documents, a conversation away.</p></div>',unsafe_allow_html=True)
        with st.container(key='suggestions'):
            cols=st.columns(3)
            prompts=[('Find a class','What is the slot for Autonomous Systems?'),('Explore a course','What does Design Thinking teach about prototyping?'),('Draft an email','Draft leave for DSL7220 for 2 days.')]
            if dataset=='demo':prompts=[('Find a class','What is the slot for EXM1000?'),('Explore a course','Find the academic policy in the synthetic handbook.'),('Draft an email','Draft leave for EXM1000 for 2 days.')]
            for col,(label,prompt) in zip(cols,prompts):
                if col.button(label,use_container_width=True,disabled=model not in available_models or not runtime_ready):suggestion=prompt
    def show_response(r,index):
        index=f'{st.session_state.session_id}-{index}'
        source_groups={}
        for evidence in r.get('citations',[]):
            group=(evidence['doc_id'],evidence['locator'],evidence['version'],evidence['text'])
            source_groups.setdefault(group,{'evidence':evidence,'ids':[]})['ids'].append(evidence['id'])
        displayed_answer=r['answer']
        for number,source in enumerate(source_groups.values(),1):
            for evidence_id in source['ids']:displayed_answer=displayed_answer.replace('['+evidence_id+']',f'[{number}]')
        if r['status'] not in ('answered','draft'):st.caption(r['status'].replace('_',' ').capitalize())
        st.markdown(displayed_answer)
        if r.get('draft'):
            d=r['draft'];st.caption('Draft — review before use · Never sent automatically')
            recipient=st.text_input('To',d['recipient'],key=f'to-{index}')
            subject=st.text_input('Subject',d['subject'],key=f'subject-{index}')
            body=st.text_area('Email body',d['body'],height=260,key=f'body-{index}')
            st.caption(' · '.join(d['missing_fields']))
            txt=f'To: {recipient}\nSubject: {subject}\n\n{body}'
            with st.expander('Copy draft'):st.code(txt,language=None)
            st.download_button('Download draft .txt',txt,file_name='academic-email-draft.txt',key=f'draft-{index}')
        if source_groups:
            with st.expander(f'Sources · {len(source_groups)}'):
                for number,source in enumerate(source_groups.values(),1):
                    e=source['evidence']
                    st.markdown(f'**[{number}] '+e['title']+'**');st.caption(f"{e['locator']} · {', '.join(source['ids'])} · version {e['version']}")
                    st.write(e['text'])
                    if e.get('source_url','').startswith(('https://','http://')):st.link_button('Official source',e['source_url'])
                    p=Path(e.get('source_path',''))
                    if p.is_file() and p.resolve().is_relative_to(ROOT/'data'):st.download_button('Open original copy',p.read_bytes(),file_name=p.name,key=f'original-{index}-{e["id"]}')
        with st.expander('Response details'):
            st.caption(f"{r['status']} · {r.get('metrics',{}).get('latency_s',0):.1f}s · trace {r['trace_id'][:10]}")
            st.json({k:v for k,v in r.get('metrics',{}).items() if k in ('tool_trace','data_calls','specialist_calls','llm_calls')})
    for i,m in enumerate(st.session_state.messages):
        st.markdown('<div class="user-turn">'+html.escape(m['question'])+'</div>',unsafe_allow_html=True)
        show_response(m['response'],i)
        st.space('medium')
    submitted=st.chat_input('Message Academic Helpdesk',disabled=model not in available_models or not runtime_ready)
    if q:=(submitted or suggestion):
        st.markdown('<div class="user-turn">'+html.escape(q)+'</div>',unsafe_allow_html=True)
        # Bounded follow-up resolution: retain the last explicit course, never infer identities.
        import re
        codes=re.findall(r'\b[A-Z]{2,4}\s?\d{4,5}\b',q)
        if codes: st.session_state.course=codes[-1].replace(' ','')
        context['course']=st.session_state.get('course','')
        query=q
        if re.search(r'\b(it|that course|this course|its)\b',q,re.I) and re.search(r'teach|instructor|meet|slot|course|credit|syllabus|prerequisite|class|leave|email',q,re.I) and context['course']:
            query+=f' [Follow-up course context: {context["course"]}]'
        with st.container():
            with st.spinner('Consulting tools and checking evidence…'):
                r=HelpdeskService().answer(query,context,mode,model,session_id=st.session_state.session_id).model_dump()
                if r['metrics'].get('resolved_course'):st.session_state.course=r['metrics']['resolved_course']
            show_response(r,len(st.session_state.messages))
        st.session_state.messages.append({'question':q,'response':r})
        st.rerun()
elif page=='Sources':
    st.subheader('An inspectable evidence library')
    st.caption(f'{approved} approved sources · Snapshot: '+(active.name if active else 'No active snapshot'))
    if active:
        manifest=pd.read_csv(active/'manifest.csv',dtype=str).fillna('')
        st.dataframe(manifest.drop(columns=['source_path'],errors='ignore'),hide_index=True)
        st.download_button('Export manifest', (active/'manifest.csv').read_bytes(),'manifest.csv')
    else: st.info('No active snapshot yet. Candidate sources are visible under Import & review.')
elif page=='Import & review':
    st.subheader('Import, inspect, approve')
    st.write('Original files are preserved. Extraction creates a private candidate snapshot. Approve only sources whose content, applicability and authority you have checked.')
    uploads=st.file_uploader('Add permitted exports',accept_multiple_files=True,type=['pdf','xlsx','docx','csv','html','txt','eml'])
    if uploads and st.button('Save selected exports'):
        dest=ROOT/'data/private_import';dest.mkdir(parents=True,exist_ok=True)
        for upload in uploads:
            p=dest/Path(upload.name).name
            if p.exists(): st.warning(f'Preserved existing file: {p.name}');continue
            p.write_bytes(upload.getvalue())
        st.success('Files saved locally.')
    if st.button('Extract a new candidate snapshot'):
        with st.spinner('Extracting all pages and workbook tabs; OCR may take several minutes…'):
            try:st.json(ingest(dataset,ROOT/('data/private_import' if dataset=='real' else 'data/demo_import')))
            except Exception as e:st.error(str(e))
    candidate=editable_candidate(dataset)
    if candidate:
        st.caption('Candidate: '+candidate.name)
        manifest=list(csv.DictReader((candidate/'manifest.csv').open(encoding='utf-8-sig')))
        review=json.loads((candidate/'review.json').read_text())
        choices={r['doc_id']:r for r in manifest if not r['duplicate_of']}
        selected=st.selectbox('Inspect source',list(choices),format_func=lambda x:choices[x]['title'])
        item=choices[selected]
        st.json({k:v for k,v in item.items() if k!='source_path'})
        p=candidate/'working'/f'{selected}.json'
        if p.exists():
            units=json.loads(p.read_text(encoding='utf-8'))
            unit=st.selectbox('Page / sheet row',range(len(units)),format_func=lambda x:units[x]['locator'])
            st.text_area('Extracted working copy',units[unit]['text'],height=300,disabled=True)
        metadata=review.get('metadata',{}).get(selected,{})
        with st.form('source-review'):
            url=st.text_input('Source URL or email identifier',metadata.get('source_url',''))
            authority=st.text_input('Issuing authority',metadata.get('authority',''))
            effective=st.text_input('Effective date / applicability note',metadata.get('effective_date',''))
            applies_program=st.text_input('Programme applicability (blank = unspecified)',metadata.get('program',''))
            applies_cohort=st.text_input('Cohort applicability (blank = unspecified)',metadata.get('cohort',''))
            completeness=st.selectbox('Completeness',['unconfirmed','complete','partial'])
            supersedes=st.text_input('Supersedes document ID (only with verified precedence)',metadata.get('supersedes',''))
            approved=st.checkbox('I reviewed source authority, extraction/OCR, table mapping and applicability',value=selected in review['approved'])
            if st.form_submit_button('Save review'):
                if approved and not authority:st.error('Enter the verified issuing authority before approval.')
                else:
                    review['approved']=sorted((set(review['approved'])|{selected}) if approved else set(review['approved'])-{selected})
                    review.setdefault('metadata',{})[selected]=dict(source_url=url,authority=authority,effective_date=effective,program=applies_program,cohort=applies_cohort,term=term,completeness=completeness,supersedes=supersedes)
                    (candidate/'review.json').write_text(json.dumps(review,indent=2),encoding='utf-8');st.success('Review saved. Rebuild to activate changes.')
        with st.expander('Workbook field mappings'):
            st.json(json.loads((candidate/'mappings.json').read_text()))
            if item['filename'].lower().endswith('.xlsx'):
                st.caption('For ambiguous or new workbook layouts, map canonical fields to original column letters. Kind: offering, timetable, faculty or slot. Values are read from the workbook; source locators are retained.')
                st.code('{"Worksheet name": {"kind": "offering", "header_row": 1, "columns": {"code": "A", "title": "B", "instructor": "E", "slot": "F"}}}',language='json')
                mapping_text=st.text_area('Custom mapping JSON','{}',key=f'mapping-{selected}')
                checked_mapping=st.checkbox('I checked these column mappings against the original worksheet',key=f'mapping-checked-{selected}')
                if st.button('Apply workbook mapping'):
                    if not checked_mapping:st.error('Review the original columns before applying a mapping.')
                    else:
                        try:
                            from helpdesk.importers.mapping import map_workbook
                            spec=json.loads(mapping_text)
                            mapped=map_workbook(item['source_path'],selected,item['version'],spec)
                            for table,new_rows in mapped.items():
                                current=json.loads((candidate/f'{table}.json').read_text(encoding='utf-8'))
                                current=[r for r in current if not (r['source_doc_id']==selected and any(r['locator'].startswith(f"'{sheet}'!") for sheet in spec))]+new_rows
                                (candidate/f'{table}.json').write_text(json.dumps(current,indent=2),encoding='utf-8')
                                write_csv(candidate/f'{table}.csv',current)
                            history_file=candidate/'custom_mappings.json'
                            history=json.loads(history_file.read_text()) if history_file.exists() else {}
                            history[selected]=spec;history_file.write_text(json.dumps(history,indent=2))
                            st.success('Mapping applied to the candidate. Review and rebuild before activation.')
                        except Exception as e:st.error(str(e))
        with st.expander('Review structured fields and completeness'):
            st.caption('Change explicit level/category/section only from verified source evidence. Every record retains its original source and row locator. Do not infer levels from code digits.')
            rows=json.loads((candidate/'records.json').read_text(encoding='utf-8'))
            if rows:
                frame=pd.DataFrame(rows)
                edited=st.data_editor(frame,disabled=[c for c in frame.columns if c not in ('level','category','section')],hide_index=True,key='table-review')
                departments=sorted(set(frame[frame.kind=='offering'].department))
                complete=st.multiselect('Departments whose entire offering list and classifications have been verified',departments,default=[d for d in review.get('complete_departments',[]) if d in departments])
                if st.button('Save structured review'):
                    corrected=edited.fillna('').to_dict('records')
                    (candidate/'records.json').write_text(json.dumps(corrected,indent=2),encoding='utf-8')
                    write_csv(candidate/'records.csv',corrected)
                    for name,kind in [('courses','offering'),('offerings','offering'),('timetable','timetable')]:write_csv(candidate/f'{name}.csv',[r for r in corrected if r['kind']==kind])
                    review['complete_departments']=complete
                    (candidate/'review.json').write_text(json.dumps(review,indent=2),encoding='utf-8')
                    st.success('Saved. Rebuild before using this snapshot.')
        if st.button('Build embeddings and activate reviewed snapshot',type='primary'):
            with st.spinner('Building local embeddings and validating index…'):
                try:
                    spec=build_index(candidate)
                    (dataset_dir(dataset)/'active.txt').write_text(str(candidate),encoding='utf-8')
                    st.success(f'Activated {spec["chunks"]} approved chunks.');st.rerun()
                except Exception as e:st.error(str(e))
elif page=='Review queue':
    st.subheader('Questions needing human review')
    with db(dataset) as connection:
        frame=pd.read_sql_query('SELECT * FROM unresolved ORDER BY timestamp DESC',connection)
        st.dataframe(frame,hide_index=True)
        st.download_button('Export redacted queue CSV',frame.to_csv(index=False),'unresolved.csv')
        if not frame.empty:
            rid=st.selectbox('Review item',frame.id.tolist())
            status=st.selectbox('Review status',['open','reviewing','resolved_by_corpus_update'])
            if st.button('Update review status'):
                connection.execute('UPDATE unresolved SET review_status=? WHERE id=?',(status,rid));connection.commit();st.rerun()
    st.caption('Resolve data gaps by importing and reviewing evidence, then rebuilding the snapshot.')
elif page=='Experiments':
    st.subheader('Measured comparisons')
    st.write('2 agent modes × 2 local models × 30 questions × 3 seeds = 360 trials. Human scoring is required for factual correctness and semantic support.')
    st.code('.\\.venv\\Scripts\\python.exe -m helpdesk evaluate --dataset real --matrix evaluation/matrix.yaml')
    runs=sorted((ROOT/'evaluation/results'/dataset).glob('*.jsonl')) if (ROOT/'evaluation/results'/dataset).exists() else []
    if runs:
        run=st.selectbox('Results file',runs,format_func=lambda p:p.name)
        results=[]
        for line in run.read_text(encoding='utf-8').splitlines():
            try:results.append(json.loads(line))
            except json.JSONDecodeError:continue # The writer may be completing its final line.
        st.progress(min(len(results)/360,1),text=f'{len(results)} of 360 trials recorded')
        columns=('id','model','mode','seed','category','status','expected_status','status_match','latency_s','peak_system_ram_bytes','timing')
        st.dataframe(pd.DataFrame([{k:r.get(k) for k in columns} for r in results]),hide_index=True)
        st.download_button('Download raw results',run.read_bytes(),run.name)
        for suffix,label in (('.metrics.json','Measured metrics'),('.changed.json','Changed outputs across repeated runs')):
            artifact=run.with_suffix(suffix)
            if artifact.exists():
                with st.expander(label):st.json(json.loads(artifact.read_text(encoding='utf-8')))
        if results:
            chosen=st.selectbox('Inspect an individual trial',range(len(results)),format_func=lambda i:f'{results[i]["id"]} · {results[i]["model"]} · {results[i]["mode"]} · seed {results[i]["seed"]}')
            with st.expander('Response, tool trace and expected evidence'):st.json(results[chosen])
        scoring=run.with_suffix('.human-scoring.csv')
        if scoring.exists():st.download_button('Download human scoring sheet',scoring.read_bytes(),scoring.name)
    else:st.info('No completed experiment output yet. No evaluation findings are assumed.')
