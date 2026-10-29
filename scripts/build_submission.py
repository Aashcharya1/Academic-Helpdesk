"""Create local submission archives without environments, models or secrets."""
import hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
dest=ROOT/'submission';dest.mkdir(exist_ok=True)
code=[]
for folder in ('helpdesk','app','scripts','tests'):
    code.extend((ROOT/folder).rglob('*.py'))
code.append(ROOT/'app/styles.css')
code.extend((ROOT/'scripts').glob('*.ps1'))
code.extend((ROOT/'evaluation').glob('*.md'))
for folder in ('report',):code.extend((ROOT/folder).glob('*.md'))
for name in ('README.md','SUBMISSION.md','Start.cmd','Start.ps1','Setup.ps1','config.yaml','requirements.txt','requirements.lock','pytest.ini','.gitignore','.gitattributes','.env.example','.streamlit/config.toml','evaluation/matrix.yaml','evaluation/freeze.json','evaluation/development-prompts.json'):
    if (ROOT/name).exists():code.append(ROOT/name)
def archive(name,paths):
    path=dest/name
    manifest=[]
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as output:
        for source in sorted(set(paths)):
            if not source.is_file():continue
            relative=source.relative_to(ROOT).as_posix()
            output.write(source,relative)
            manifest.append({'path':relative,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
        output.writestr('ARCHIVE_MANIFEST.json',json.dumps(manifest,indent=2))
    with zipfile.ZipFile(path) as check:
        if check.testzip():raise RuntimeError('Archive integrity verification failed')
    return {'file':str(path),'files':len(manifest),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
result=[archive('Academic-Helpdesk-code.zip',code)]
private=[]
for folder in ('data/private_import','data/audit','evaluation/results','report/private'):
    private.extend((ROOT/folder).rglob('*'))
for name in ('evaluation/questions.jsonl','DESIGN.pdf'):
    private.append(ROOT/name)
private.extend((ROOT/'data').glob('*.json'))
active=ROOT/'data/real/active.txt'
if active.exists():
    snapshot=Path(active.read_text(encoding='utf-8'))
    private.extend(snapshot.glob('*.json'));private.extend(snapshot.glob('*.csv'))
    private.extend((snapshot/'working').glob('*.json'))
result.append(archive('Academic-Helpdesk-private-evidence.zip',private))
(dest/'archives.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
