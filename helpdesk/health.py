import json
from .config import ROOT

def is_ready(model,mode):
    path=ROOT/'.cache/runtime-ready.json'
    if not path.exists():return False
    try:return bool(json.loads(path.read_text(encoding='utf-8')).get(f'{model}/{mode}',{}).get('passed'))
    except (OSError,json.JSONDecodeError):return False
