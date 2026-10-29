import importlib.metadata, json, platform, shutil, sys, time, subprocess
import psutil, requests
from .config import ROOT,CONFIG
from .importers import snapshot

def doctor(inference=False):
    result={'python':sys.version,'platform':platform.platform(),'ram':dict(psutil.virtual_memory()._asdict()),'disk':dict(zip(('total','used','free'),shutil.disk_usage(ROOT))),'model_directory':'F:\\Ollama\\models','dependencies':{},'models':[]}
    for executable,args in (('git',['--version']),('ollama',['--version'])):
        path=shutil.which(executable)
        result[executable]={'path':path}
        if path:
            checked=subprocess.run([path,*args],cwd=ROOT,capture_output=True,text=True,timeout=15)
            result[executable].update(version=(checked.stdout+checked.stderr).strip(),exit_code=checked.returncode)
    for name in ('google-adk','litellm','chromadb','streamlit','pymupdf','rapidocr','onnxruntime','openpyxl'):
        try: result['dependencies'][name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: result['dependencies'][name]='missing'
    try:
        r=requests.get(CONFIG['ollama_url']+'/api/tags',timeout=5);r.raise_for_status();result['models']=r.json()['models']
        import hashlib
        result['api_disk_manifest_matches']={}
        for entry in result['models']:
            name,tag=entry['name'].split(':',1)
            p=__import__('pathlib').Path('F:/Ollama/models/manifests/registry.ollama.ai/library')/name/tag
            result['api_disk_manifest_matches'][entry['name']]=p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==entry['digest']
        if sys.platform=='win32':
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as key:result['persistent_user_OLLAMA_MODELS']=winreg.QueryValueEx(key,'OLLAMA_MODELS')[0]
        if inference:
            for m in CONFIG['chat_models']:
                if m not in {e['name'] for e in result['models']}:
                    result[m]={'status':'not_available'};continue
                start=time.monotonic()
                body={'model':m,'stream':False,'think':False,'messages':[{'role':'user','content':'Use the ping tool with value hello.'}],'tools':[{'type':'function','function':{'name':'ping','description':'Return the input','parameters':{'type':'object','properties':{'value':{'type':'string'}},'required':['value']}}}],'options':{'num_ctx':2048,'num_predict':100,'temperature':0.2,'num_gpu':0,'num_thread':6},'keep_alive':0}
                r=requests.post(CONFIG['ollama_url']+'/api/chat',json=body,timeout=240);r.raise_for_status()
                calls=r.json().get('message',{}).get('tool_calls',[])
                verified=any(call.get('function',{}).get('name')=='ping' and call.get('function',{}).get('arguments',{}).get('value')=='hello' for call in calls)
                result[m]={'seconds':time.monotonic()-start,'actual_inference':r.json(),'tool_call_verified':verified}
            from .rag import embed
            result['embedding_probe']={'dimensions':len(embed(['academic registration'])[0])}
    except Exception as e: result['runtime_error']=str(e)
    for dataset in ('real','demo'):
        p=snapshot(dataset)
        result[dataset]={'snapshot':str(p) if p else None}
        if p:result[dataset]['review']=json.loads((p/'review.json').read_text())
    return result
