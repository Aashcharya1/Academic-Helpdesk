import os,sys,faulthandler,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.pop('SSLKEYLOGFILE',None)
faulthandler.dump_traceback_later(40,repeat=False)
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from helpdesk.schemas import Response
from helpdesk.tools import draft_email
class OfflineModels:
    def json(self):return {'models':[{'name':'qwen3:8b'},{'name':'llama3.1:8b'}]}
print('Starting component test with API mocked; no browser or network access.',flush=True)
with patch('requests.get',return_value=OfflineModels()),patch('helpdesk.health.is_ready',return_value=True):
    app=AppTest.from_file(str(ROOT/'app/main.py')).run(timeout=30)
    initial_session=app.session_state['session_id']
    app.session_state['course']='SYNTH1000'
    app.sidebar.selectbox[0].select('demo').run(timeout=30)
    context_reset=app.session_state['session_id']!=initial_session and 'course' not in app.session_state
    fixture=Response(request_id='synthetic-ui-test',trace_id='synthetic-ui-test',status='draft',answer='Synthetic UI fixture — no model inference.',draft=draft_email('leave','[instructor email]','',''))
    with patch('helpdesk.service.HelpdeskService.answer',return_value=fixture):
        app.chat_input[0].set_value('Draft a synthetic academic leave email.').run(timeout=30)
    draft_editor_present=any(t.label=='Email body' for t in app.text_area)
    conversation_retained=bool(app.session_state['messages'])
    navigation=[];exceptions=[e.message for e in app.exception]
    for page in ['Sources','Import & review','Review queue','Experiments','Chat']:
        app.sidebar.radio[0].set_value(page).run(timeout=30)
        navigation.append(page);exceptions.extend(e.message for e in app.exception)
    new_chat=next(b for b in app.sidebar.button if b.label=='New chat')
    new_chat.click().run(timeout=30)
    new_chat_clears=not app.session_state['messages'] and 'course' not in app.session_state
result={'exceptions':exceptions,'navigation':navigation,'tabs':[],'context_reset':context_reset,'conversation_retained':conversation_retained,'new_chat_clears':new_chat_clears,'draft_editor_present':draft_editor_present,'no_send_button':not any(b.label.lower()=='send' for b in app.button),'scope':'Offline component tests with mocked API health and a synthetic draft response; not model/browser validation.'}
print(json.dumps(result),flush=True)
(ROOT/'report/private/ui-components.json').write_text(json.dumps(result,indent=2))
faulthandler.cancel_dump_traceback_later()
if result['exceptions'] or not context_reset or not draft_editor_present or not new_chat_clears:raise SystemExit(1)
