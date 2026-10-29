import csv, hashlib, json, re
from pathlib import Path
import requests
from ..config import CONFIG
from ..importers import snapshot
from ..schemas import Evidence

DOC_PREFIX='title: academic document | text: '
QUERY_PREFIX='task: search result | query: '

def model_digest():
    result=requests.get(CONFIG['ollama_url']+'/api/tags',timeout=10)
    result.raise_for_status()
    model=next((m for m in result.json()['models'] if m['name']==CONFIG['embedding_model']),None)
    if not model:raise ValueError('Embedding model is unavailable')
    return model['digest']

def tokens(s):
    return re.findall(r'[a-z0-9]+',s.lower())

def embed(texts, query=False):
    prefix = QUERY_PREFIX if query else DOC_PREFIX
    r=requests.post(CONFIG['ollama_url']+'/api/embed',json={'model':CONFIG['embedding_model'],'input':[prefix+t for t in texts],'keep_alive':'5m','options':{'num_gpu':0,'num_thread':4}},timeout=180)
    r.raise_for_status()
    return r.json()['embeddings']

def collection(path, name=None):
    import chromadb
    from chromadb.config import Settings
    if name is None:
        spec=json.loads((path/'index.json').read_text(encoding='utf-8')) if (path/'index.json').exists() else {}
        name=spec.get('collection','academic')
    client=chromadb.PersistentClient(path=str(path/'chroma'),settings=Settings(anonymized_telemetry=False))
    return client.get_or_create_collection(name,metadata={'hnsw:space':'cosine'},embedding_function=None)

def fingerprint(path):
    digest=hashlib.sha256()
    for name in ('review.json','records.json','faculty.json','slots.json','gaps.json','chunks.json'):
        p=path/name
        if p.exists(): digest.update(name.encode()+p.read_bytes())
    return digest.hexdigest()

def reviewed_chunks(path):
    review=json.loads((path/'review.json').read_text(encoding='utf-8'))
    approved=set(review['approved']); metadata=review.get('metadata',{})
    out=[]
    for c in json.loads((path/'chunks.json').read_text(encoding='utf-8')):
        if c['doc_id'] in approved and c['locator'] not in metadata.get(c['doc_id'],{}).get('excluded_locators',[]):
            c.update({k:v for k,v in metadata.get(c['doc_id'],{}).items() if k in ('term','program','cohort','source_url')})
            out.append(c)
    return out

def build_index(path):
    path=Path(path); chunks=reviewed_chunks(path)
    if not chunks: raise ValueError('No approved chunks. Review sources first.')
    digest=model_digest()
    collection_name='academic-'+digest[:12]+'-'+hashlib.sha256(DOC_PREFIX.encode()).hexdigest()[:6]
    col=collection(path,collection_name)
    existing=set(col.get()['ids'])
    stale=existing-{c['id'] for c in chunks}
    if stale: col.delete(ids=list(stale))
    cache=path/'embedding_cache'; cache.mkdir(exist_ok=True)
    for start in range(0,len(chunks),12):
        batch=[c for c in chunks[start:start+12] if c['id'] not in existing]
        if not batch: continue
        vectors=[]; missing=[]; cache_paths=[]
        for c in batch:
            key=hashlib.sha256((CONFIG['embedding_model']+digest+DOC_PREFIX+c['text']).encode()).hexdigest()
            p=cache/f'{key}.json'
            cache_paths.append(p)
            if p.exists(): vectors.append(json.loads(p.read_text()))
            else:
                missing.append(len(vectors));vectors.append(None)
        if missing:
            fresh=embed([batch[i]['text'] for i in missing])
            for i,vec in zip(missing,fresh):
                vectors[i]=vec;cache_paths[i].write_text(json.dumps(vec))
        col.upsert(ids=[c['id'] for c in batch],embeddings=vectors,documents=[c['text'] for c in batch],metadatas=[{'doc_id':c['doc_id'],'version':c['version']} for c in batch])
    spec={'embedding_model':CONFIG['embedding_model'],'embedding_digest':digest,'collection':collection_name,'document_prefix':DOC_PREFIX,'query_prefix':QUERY_PREFIX,'chunks':len(chunks),'review_sha256':fingerprint(path)}
    (path/'index.json').write_text(json.dumps(spec,indent=2))
    return spec

class Retriever:
    def __init__(self,dataset,context):
        self.path=snapshot(dataset); self.context=context
        if self.path:
            spec=json.loads((self.path/'index.json').read_text())
            if spec.get('review_sha256')!=fingerprint(self.path):raise ValueError('Snapshot changed; rebuild and activate before answering')
        self.chunks=reviewed_chunks(self.path) if self.path else []
        self.by_id={c['id']:c for c in self.chunks}

    def applicable(self,c):
        return all(not c.get(k) or not self.context.get(k) or str(c[k])==str(self.context[k]) for k in ('term','program','cohort'))

    def search(self,question,k=6):
        if not self.path or not self.chunks: return []
        spec=json.loads((self.path/'index.json').read_text())
        if spec['embedding_model']!=CONFIG['embedding_model']: raise ValueError('Embedding model changed; rebuild required')
        if spec.get('embedding_digest')!=model_digest() or spec.get('document_prefix')!=DOC_PREFIX or spec.get('query_prefix')!=QUERY_PREFIX:raise ValueError('Embedding model digest/task format changed; rebuild required')
        if spec.get('review_sha256')!=fingerprint(self.path): raise ValueError('Source review changed; rebuild index before querying')
        from rank_bm25 import BM25Okapi
        valid=[c for c in self.chunks if self.applicable(c)]
        if not valid: return []
        bm=BM25Okapi([tokens(c['text']) for c in valid])
        scores=bm.get_scores(tokens(question))
        lexical=sorted(range(len(valid)),key=lambda i:scores[i],reverse=True)[:8]
        col=collection(self.path)
        dense=col.query(query_embeddings=embed([question],True),n_results=min(32,col.count()))
        dense_ids=[i for i in dense['ids'][0] if i in self.by_id and self.applicable(self.by_id[i])][:8]
        fused={}
        for ranking in ([valid[i]['id'] for i in lexical if scores[i]>0],dense_ids):
            for rank,i in enumerate(ranking): fused[i]=fused.get(i,0)+1/(60+rank+1)
        result=[]
        for i in sorted(fused,key=fused.get,reverse=True)[:min(k,6)]:
            c=self.by_id[i]
            # Similarity ranking is candidate selection, not a claim of confidence.
            result.append(Evidence(**{key:c[key] for key in Evidence.model_fields if key in c},retrieval_score=fused[i]))
        return result
