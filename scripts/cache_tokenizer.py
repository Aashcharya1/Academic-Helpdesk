"""Cache LiteLLM's tokenizer table from its official URL, with pinned SHA-256."""
import concurrent.futures,hashlib,os,shutil,tempfile,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
os.environ.pop('SSLKEYLOGFILE',None)
URL='https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken'
EXPECTED='223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7'
key=hashlib.sha1(URL.encode()).hexdigest()
dest=ROOT/'.cache/tiktoken'/key;dest.parent.mkdir(parents=True,exist_ok=True)
for candidate in (dest,Path(tempfile.gettempdir())/'data-gym-cache'/key,Path.home()/'.cache/tiktoken'/key):
    if candidate.exists() and hashlib.sha256(candidate.read_bytes()).hexdigest()==EXPECTED:
        if candidate!=dest:shutil.copyfile(candidate,dest)
        print('Verified tokenizer cache reused',flush=True);raise SystemExit(0)
with urllib.request.urlopen(urllib.request.Request(URL,method='HEAD'),timeout=30) as response:size=int(response.headers['Content-Length'])
parts=ROOT/'.cache/tokenizer-parts';parts.mkdir(exist_ok=True)
step=128*1024
def fetch(start):
    end=min(size,start+step);p=parts/str(start)
    if p.exists() and p.stat().st_size==end-start:return p
    for attempt in range(6):
        try:
            req=urllib.request.Request(URL,headers={'Range':f'bytes={start}-{end-1}'})
            with urllib.request.urlopen(req,timeout=30) as r:
                if r.status!=206:raise ValueError('Expected a ranged response')
                data=r.read()
            if len(data)!=end-start:raise ValueError('Short tokenizer range')
            p.write_bytes(data);return p
        except Exception:
            if attempt==5:raise
            time.sleep(2)
with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:files=list(pool.map(fetch,range(0,size,step)))
payload=b''.join(p.read_bytes() for p in files)
if hashlib.sha256(payload).hexdigest()!=EXPECTED:raise ValueError('Tokenizer checksum mismatch')
dest.write_bytes(payload)
print('Official tokenizer table cached and SHA-256 verified',flush=True)
