"""Resumable official Ollama registry download using small verified ranges.

Use when long Ollama transfers repeatedly reset on the local connection. Existing
Ollama partial ranges are reused only up to recorded completed byte counts. Final
blobs must pass the official registry SHA-256 before their manifest is activated.
"""
import concurrent.futures,hashlib,json,os,threading,time,urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
os.environ.pop('SSLKEYLOGFILE',None)
MODELS=Path('F:/Ollama/models')
STATE=ROOT/'.cache/model-ranges';STATE.mkdir(parents=True,exist_ok=True)
ALLOWED=('embeddinggemma:300m','qwen3:8b','llama3.1:8b')
BASE='https://registry.ollama.ai/v2/library/'
SEGMENT=2*1024*1024

def digest_file(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while chunk:=f.read(8*1024*1024):h.update(chunk)
    return h.hexdigest()

def fetch_bytes(url,start=None,end=None):
    headers={'User-Agent':'AcademicHelpdesk-local-setup/1.0'}
    if start is not None:headers['Range']=f'bytes={start}-{end}'
    req=urllib.request.Request(url,headers=headers)
    with urllib.request.urlopen(req,timeout=45) as r:
        if start is not None and r.status!=206:raise RuntimeError('Server did not honor byte range')
        data=r.read()
    if start is not None and len(data)!=end-start+1:raise RuntimeError('Short range')
    return data

def retry_fetch(url,start=None,end=None):
    for attempt in range(8):
        try:return fetch_bytes(url,start,end)
        except Exception:
            if attempt==7:raise
            time.sleep(min(2**attempt,15))

def blob(name,entry):
    digest=entry['digest'];size=entry['size']
    if not digest.startswith('sha256:') or len(digest)!=71:raise ValueError('Invalid official digest')
    key=digest.replace(':','-');target=MODELS/'blobs'/key
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists() and target.stat().st_size==size and digest_file(target)==digest[7:]:
        print(key[:20]+' verified existing',flush=True);return
    url=BASE+name+'/blobs/'+digest
    if size<SEGMENT:
        data=retry_fetch(url)
        if hashlib.sha256(data).hexdigest()!=digest[7:]:raise RuntimeError('Small blob checksum mismatch')
        target.write_bytes(data);return
    temp=target.with_name(key+'-range-download')
    # Resolve the registry's official CDN redirect once per recovery round.
    # Reusing it avoids thousands of redundant registry TLS handshakes.
    try:
        with urllib.request.urlopen(urllib.request.Request(url,method='HEAD'),timeout=45) as response:
            url=response.geturl()
    except Exception:pass
    if not temp.exists():
        with temp.open('wb') as f:f.truncate(size)
    marks=STATE/key;marks.mkdir(exist_ok=True)
    old=target.with_name(key+'-partial')
    intervals=[]
    if old.exists():
        for p in old.parent.glob(key+'-partial-*'):
            try:
                part=json.loads(p.read_text());intervals.append((part['Offset'],part['Offset']+part['Completed']))
            except Exception:pass
    counter=0;guard=threading.Lock();total=(size+SEGMENT-1)//SEGMENT;start_time=time.monotonic()
    def part(offset):
        nonlocal counter
        end=min(size,offset+SEGMENT);marker=marks/f'{offset}.done'
        valid=False
        if marker.exists():
            with temp.open('rb') as f:f.seek(offset);old_data=f.read(end-offset)
            valid=hashlib.sha256(old_data).hexdigest()==marker.read_text()
        if not valid:
            if old.exists() and any(a<=offset and end<=b for a,b in intervals):
                with old.open('rb') as f:f.seek(offset);data=f.read(end-offset)
            else:data=retry_fetch(url,offset,end-1)
            if len(data)!=end-offset:raise RuntimeError('Invalid block length')
            with temp.open('r+b') as f:f.seek(offset);f.write(data);f.flush()
            marker.write_text(hashlib.sha256(data).hexdigest())
        with guard:
            counter+=1
            if counter%25==0 or counter==total:
                elapsed=time.monotonic()-start_time
                print(f'{name} {counter}/{total} blocks ({counter/total:.1%}) elapsed {elapsed:.0f}s',flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=48) as pool:
        list(pool.map(part,range(0,size,SEGMENT)))
    if digest_file(temp)!=digest[7:]:raise RuntimeError('Final model SHA-256 mismatch. Preserve ranges for diagnosis.')
    temp.replace(target)
    print(key[:20]+' full SHA-256 verified',flush=True)

for model in ALLOWED:
    name,tag=model.split(':')
    for recovery in range(20):
        try:
            manifest_bytes=retry_fetch(BASE+name+'/manifests/'+tag)
            manifest=json.loads(manifest_bytes)
            for entry in [manifest['config']]+manifest['layers']:blob(name,entry)
            dest=MODELS/'manifests/registry.ollama.ai/library'/name/tag
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(manifest_bytes)
            print(model+' activated verified manifest',flush=True)
            break
        except Exception as error:
            print(f'{model} recovery {recovery+1}: {type(error).__name__}: {error}. Completed blocks retained.',flush=True)
            if recovery==19:raise
            time.sleep(5)
print('All requested official models verified on disk',flush=True)
