import json
from .config import ROOT
from .rag import Retriever,collection
from .schemas import Context
from .tools import DataTools

def verify_data(dataset):
    context=Context(dataset=dataset).model_dump()
    retriever=Retriever(dataset,context)
    if not retriever.path:raise AssertionError('No active corpus')
    data=DataTools(dataset,context,retriever)
    checks={}
    checks['approved_chunks']=len(retriever.chunks)
    checks['chroma_vectors']=collection(retriever.path).count()
    assert checks['approved_chunks']==checks['chroma_vectors']
    if dataset=='demo':
        hits=retriever.search('EXM1000 Introduction to Examples')
        checks['retrieval']=[e.model_dump() for e in hits]
        assert hits and all('DEMO' in e.title for e in hits)
        checks['EXM1000']=data.schedule('EXM1000').model_dump()
        assert checks['EXM1000']['status']=='ok'
        assert data.schedule('CSL7650').status=='not_found'
        checks['passed']=True
        destination=ROOT/'report/private/data-smoke-demo.json';destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(json.dumps(checks,indent=2,ensure_ascii=False),encoding='utf-8')
        return {'passed':True,'approved_chunks':checks['approved_chunks'],'chroma_vectors':checks['chroma_vectors'],'retrieval_hits':len(hits),'details':'report/private/data-smoke-demo.json'}
    query='What does Design Thinking teach about prototyping?'
    hits=retriever.search(query)
    checks['retrieval']=[e.model_dump() for e in hits]
    assert any('Design Thinking' in e.title for e in hits),'Development retrieval failed to find expected source'
    for course in ('Autonomous Systems','CSL7570','DSL7220','AIL7260'):
        checks[course]={'schedule':data.schedule(course).model_dump(),'instructor':data.instructor(course).model_dump()}
    assert checks['Autonomous Systems']['schedule']['status']=='ok'
    assert checks['CSL7570']['schedule']['status']=='not_found'
    assert checks['DSL7220']['instructor']['status']=='ok'
    assert checks['AIL7260']['schedule']['status']=='ambiguous'
    assert checks['AIL7260']['instructor']['data']['co_teacher_review']
    assert data.count('SoLA','400','elective').status=='incomplete'
    checks['overlap']=data.compare('CSL7650','DSL7560').model_dump()
    assert checks['overlap']['status']=='ok' and not checks['overlap']['data']['overlap']
    checks['passed']=True
    (ROOT/'report/private').mkdir(parents=True,exist_ok=True)
    (ROOT/'report/private/data-smoke.json').write_text(json.dumps(checks,indent=2,ensure_ascii=False),encoding='utf-8')
    return {'passed':True,'approved_chunks':checks['approved_chunks'],'chroma_vectors':checks['chroma_vectors'],'retrieval_hits':len(hits),'details':'report/private/data-smoke.json'}
