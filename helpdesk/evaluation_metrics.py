"""Measured machine checks and explicitly incomplete human-scored metrics."""
import csv,json,math,statistics
from pathlib import Path

def summarize(runs,scoring_path=None):
    def ratio(a,b):return a/b if b else None
    groups={}
    for row in runs:groups.setdefault((row['model'],row['mode']),[]).append(row)
    output={}
    scores=[]
    if scoring_path and Path(scoring_path).exists():
        scores=list(csv.DictReader(Path(scoring_path).open(encoding='utf-8-sig')))
    for (model,mode),rows in groups.items():
        durations=sorted(row['latency_s'] for row in rows)
        factual=[row for row in rows if row['expected_status']=='answered']
        oos=[row for row in rows if row['expected_status']=='out_of_scope']
        emails=[row for row in rows if row['expected_status']=='draft']
        retrieval=[row for row in rows if row.get('retrieval_gold_total')]
        group_scores=[row for row in scores if row['model']==model and row['mode']==mode]
        factual_ids={(r['id'],str(r['seed'])) for r in factual}
        factual_scores=[r for r in group_scores if (r['id'],r['seed']) in factual_ids]
        def sum_score(field):
            values=[row.get(field,'') for row in group_scores]
            return sum(float(v) for v in values) if values and all(v.strip() for v in values) else None
        def human_ratio(numerator,denominator):
            n,d=sum_score(numerator),sum_score(denominator)
            return ratio(n,d) if n is not None and d is not None else None
        accuracy=None
        if factual_scores and len(factual_scores)==len(factual) and all(r.get('fully_correct','').strip() for r in factual_scores):
            accuracy=sum(float(r['fully_correct']) for r in factual_scores)/len(factual)
        metrics={'trials':len(rows),'runtime_errors':sum(r['status']=='error' for r in rows),
          'status_match_count':sum(r['status_match'] for r in rows),
          'oos_refusal_recall':ratio(sum(r['status']=='out_of_scope' for r in oos),len(oos)),
          'false_refusal_rate_by_candidate_gold':ratio(sum(r['status'] in ('out_of_scope','insufficient_evidence','needs_clarification') for r in factual),len(factual)),
          'email_draft_tool_completion_rate':ratio(sum(r['status']=='draft' and any(c['tool']=='create_email_draft' for c in r['response']['metrics'].get('tool_trace',[])) for r in emails),len(emails)),
          'retrieval_candidate_gold_recall':ratio(sum(r['retrieval_gold_hits'] for r in retrieval),sum(r['retrieval_gold_total'] for r in retrieval)),
          'retrieval_evaluated_trials':len(retrieval),'median_latency_s':statistics.median(durations),
          'p95_latency_s':durations[math.ceil(.95*len(durations))-1],
          'peak_system_ram_bytes':max(r['peak_system_ram_bytes'] for r in rows),
          'factual_accuracy_human':accuracy,'groundedness_human':human_ratio('supported_claims','total_claims'),
          'citation_precision_human':human_ratio('supporting_citations','total_citations'),
          'citation_coverage_human':human_ratio('cited_claims','total_claims'),
          'human_review':'pending unless every required cell is completed; candidate gold needs human adjudication'}
        for residency in ('model resident before request','model not resident before request'):
            times=[r['latency_s'] for r in rows if r.get('timing')==residency]
            metrics[residency]={'trials':len(times),'median_latency_s':statistics.median(times) if times else None}
        output[model+'/'+mode]=metrics
    return output

def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('results');parser.add_argument('--scoring')
    args=parser.parse_args();path=Path(args.results)
    rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    result=summarize(rows,args.scoring)
    path.with_suffix('.metrics.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
