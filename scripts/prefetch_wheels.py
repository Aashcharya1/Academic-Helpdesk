"""Download pip's exact resolved wheels concurrently with verified SHA-256.

Only official files.pythonhosted.org URLs from pip's resolution report are accepted.
Range segments are persisted in the project cache to resume slow connections.
"""
import concurrent.futures,hashlib,json,os,time,urllib.request,sys,re
from pathlib import Path
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]
os.environ.pop('SSLKEYLOGFILE',None)
CACHE=ROOT/'.cache';OUT=CACHE/'wheels';PARTS=CACHE/'wheel-parts'
OUT.mkdir(parents=True,exist_ok=True);PARTS.mkdir(parents=True,exist_ok=True)
plan=json.loads((CACHE/'requirements-plan.json').read_text())
if len(sys.argv)>1:
    from pip._vendor.packaging.tags import sys_tags
    from pip._vendor.packaging.utils import parse_wheel_filename
    supported=set(sys_tags())
    for requirement in sys.argv[1:]:
        if not re.fullmatch(r'[A-Za-z0-9_.-]+==[A-Za-z0-9_.-]+',requirement):raise ValueError('Use an exact package==version')
        package,version=requirement.split('==')
        with urllib.request.urlopen(f'https://pypi.org/pypi/{package}/{version}/json',timeout=30) as response:metadata=json.load(response)
        candidates=[u for u in metadata['urls'] if u['filename'].endswith('.whl') and parse_wheel_filename(u['filename'])[3]&supported]
        if not candidates:raise ValueError('No compatible official wheel for '+requirement)
        wheel=candidates[0]
        plan['install'].append({'download_info':{'url':wheel['url'],'archive_info':{'hashes':{'sha256':wheel['digests']['sha256']}}}})
items=[]
for item in plan['install']:
    url=item['download_info']['url']
    if urlparse(url).hostname!='files.pythonhosted.org':raise ValueError('Non-PyPI download rejected')
    name=urlparse(url).path.rsplit('/',1)[-1]
    if not name.endswith('.whl'):raise ValueError('Use wheel-only resolution')
    digest=item['download_info']['archive_info']['hashes']['sha256']
    items.append((url,name,digest))
cached={}
for p in (CACHE/'pip').rglob('*.body'):
    if p.stat().st_size>500:
        cached[hashlib.sha256(p.read_bytes()).hexdigest()]=p
old_cache=CACHE/'pip/http'
if old_cache.exists():
    from pip._vendor import msgpack
    recovered=CACHE/'recovered-wheels';recovered.mkdir(exist_ok=True)
    for p in old_cache.rglob('*'):
        if not p.is_file() or p.stat().st_size<500:continue
        try:
            payload=msgpack.loads(p.read_bytes()[5:],raw=False)['response']['body']
            if not payload.startswith(b'PK'):continue
            digest=hashlib.sha256(payload).hexdigest()
            target=recovered/digest
            if not target.exists():target.write_bytes(payload)
            cached[digest]=target
        except Exception:pass

def download(item):
    url,name,digest=item;target=OUT/name
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==digest:return name+' cached'
    if digest in cached:
        import shutil
        shutil.copyfile(cached[digest],target);return name+' reused pip cache'
    for retry in range(4):
        try:
            req=urllib.request.Request(url,method='HEAD')
            with urllib.request.urlopen(req,timeout=30) as r:size=int(r.headers['Content-Length'])
            break
        except Exception:
            if retry==3:raise
            time.sleep(2)
    segment=2*1024*1024
    def part(offset):
        end=min(size-1,offset+segment-1);p=PARTS/f'{digest}-{offset}'
        if p.exists() and p.stat().st_size==end-offset+1:return p
        for retry in range(5):
            try:
                req=urllib.request.Request(url,headers={'Range':f'bytes={offset}-{end}'})
                with urllib.request.urlopen(req,timeout=45) as r:
                    if r.status!=206 and size>segment:raise ValueError('Range request not honored')
                    with p.open('wb') as f:
                        while data:=r.read(131072):f.write(data)
                if p.stat().st_size!=end-offset+1:raise ValueError('Short range')
                return p
            except Exception:
                if retry==4:raise
                time.sleep(2)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8 if size>segment else 2) as pool:
        paths=list(pool.map(part,range(0,size,segment)))
    temp=target.with_suffix('.download')
    with temp.open('wb') as f:
        for p in paths:
            with p.open('rb') as source:
                while data:=source.read(1024*1024):f.write(data)
    if hashlib.sha256(temp.read_bytes()).hexdigest()!=digest:raise ValueError('SHA-256 mismatch: '+name)
    temp.replace(target)
    return name+' verified'

with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
    futures=[pool.submit(download,item) for item in items]
    for future in concurrent.futures.as_completed(futures):print(future.result(),flush=True)
print('All resolved wheels verified',flush=True)
