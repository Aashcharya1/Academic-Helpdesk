import os
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
# Do not inherit TLS secret logging to an unrelated drive-root debug file.
os.environ.pop('SSLKEYLOGFILE', None)
os.environ.setdefault('OLLAMA_API_BASE', 'http://127.0.0.1:11434')
os.environ.setdefault('ANONYMIZED_TELEMETRY', 'False')
os.environ.setdefault('HF_HOME', str(ROOT / '.cache/huggingface'))
os.environ.setdefault('LITELLM_LOCAL_MODEL_COST_MAP', 'True')
os.environ.setdefault('TIKTOKEN_CACHE_DIR', str(ROOT / '.cache/tiktoken'))
os.environ.setdefault('CUSTOM_TIKTOKEN_CACHE_DIR', str(ROOT / '.cache/tiktoken'))
os.environ.setdefault('XDG_CACHE_HOME', str(ROOT / '.cache'))
CONFIG = yaml.safe_load((ROOT / 'config.yaml').read_text())

def dataset_dir(dataset: str) -> Path:
    if dataset not in ('real', 'demo'):
        raise ValueError('Unknown dataset')
    p = ROOT / 'data' / dataset
    p.mkdir(parents=True, exist_ok=True)
    return p
