"""Generate a factual execution report from saved checks and raw trial outputs."""
import csv,json,re,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(path,default=None):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError,json.JSONDecodeError):return default
private=ROOT/'report/private';private.mkdir(parents=True,exist_ok=True)
doctor=load(private/'doctor.json',{})
ui=load(private/'ui-components.json',{})
data=load(private/'data-smoke.json',{})
testlog=(ROOT/'tests.log').read_text(encoding='utf-8') if (ROOT/'tests.log').exists() else ''
passed=re.search(r'(\d+) passed',testlog)
test_summary=(passed[1]+' passed') if passed else 'Not verified; inspect tests.log'
active_file=ROOT/'data/real/active.txt'
active=Path(active_file.read_text(encoding='utf-8')) if active_file.exists() else None
review=load(active/'review.json',{}) if active else {}
manifest=list(csv.DictReader((active/'manifest.csv').open(encoding='utf-8-sig'))) if active else []
raw_files=sorted((ROOT/'evaluation/results/real').glob('*.jsonl')) if (ROOT/'evaluation/results/real').exists() else []
runs=[]
run_state={}
if raw_files:
    run_state=load(raw_files[-1].with_suffix('.checkpoint.json'),{})
    for line in raw_files[-1].read_text(encoding='utf-8').splitlines():
        try:runs.append(json.loads(line))
        except json.JSONDecodeError:pass
smokes=[]
for p in sorted(private.glob('smoke-*.json')):
    rows=load(p,[])
    smokes.append((p.name,len(rows),sum(r['passed'] for r in rows),round(statistics.median(r['response']['metrics']['latency_s'] for r in rows),2) if rows else None))
models={m['name']:m for m in doctor.get('models',[])}
rows=['# Academic Helpdesk: implementation and measured validation','',
'The application runs locally at http://127.0.0.1:8501. Original academic exports remain private and unchanged. This report distinguishes executed checks from pending model trials and human review.','',
'## Environment','',
f'- Python: {doctor.get("python","not recorded").splitlines()[0]}.',
f'- Platform: {doctor.get("platform","not recorded")}.',
f'- Persistent user OLLAMA_MODELS: {doctor.get("persistent_user_OLLAMA_MODELS","not verified")}.',
'- Dependencies are installed in the project virtual environment and pinned in requirements.lock. pip check was executed separately; see setup logs.',
'- Model transfers use official Ollama manifests and complete SHA-256 checks; interrupted small ranges are retained in the project cache.','',
'Chat currently uses six CPU threads (`num_gpu=0`) after native GPU cold-start failures on the 4 GB laptop GPU. Embeddings use four CPU threads. The host prompt cache is capped at 512 MiB. The requested 8B models have not been substituted.','',
'| Requested model | Downloaded size (GB) | API availability | Quantization | Actual inference |','|---|---:|---|---|---|']
for name in ('qwen3:8b','embeddinggemma:300m','llama3.1:8b'):
    m=models.get(name,{})
    probe=doctor.get(name,{})
    inference=('embedding probe: '+str(doctor['embedding_probe']['dimensions'])+' dimensions') if name.startswith('embedding') and 'embedding_probe' in doctor else ('tool call verified' if probe.get('tool_call_verified') else 'not verified')
    size=round(m['size']/1e9,2) if m.get('size') else 'not verified'
    rows.append(f'| {name} | {size} | {"available" if m else "not yet verified"} | {m.get("details",{}).get("quantization_level","unknown")} | {inference} |')
rows+=['','## Corpus and application','',
'- The UI uses plain black/grey, installed Segoe UI fonts, a pinned bottom composer, native follow-output scrolling and a narrow reading column. Source cards and response details are collapsed. Administration is separated into sidebar pages.',
f'- Supplied files: {len(manifest)}; distinct hashes: {sum(not r["duplicate_of"] for r in manifest)}; approved for retrieval by builder review: {len(review.get("approved",[]))}. Final human applicability review remains separate.',
f'- Indexed chunks: {data.get("chroma_vectors","not verified")}. Real embeddings and hybrid retrieval data smoke check: {data.get("passed",False)}.',
'- All workbook tabs are extracted. Structured records retain source document/hash, worksheet and row/cell locator. Missing values are blank/unknown; a code digit is never used to infer course level.',
'- Scanned pages use cached local OCR assets. Corrected English transcriptions retain the raw OCR working text and original PDFs.',
'- EML bodies and attachments, PDF, DOCX, XLSX/CSV and HTML/TXT loaders are implemented. Custom workbook column mapping is available in the local review UI.',
'- Baseline: one ADK LlmAgent with approved tools. Multiagent: root plus policy, schedule and email AgentTool specialists, with shared model and bounded sequential execution.',
'- Backends validate returned evidence IDs/quotes, snapshot fingerprints, unresolved-source conflicts and request budgets. Factual output uses source excerpts and deterministic structured values. Semantic relevance is not established by ID validation alone.',
'- Email is editable draft-only. Unknown contacts and identity/dates remain placeholders; multiple instructors require recipient review. No sending API or Send button exists.',
'- REAL and DEMO use separate snapshots, indexes, state and results. Context changes clear chat/course context. No silent fallback or chat web search exists.','',
'## Executed checks','',
f'- Automated backend/loader/contract tests: {test_summary}.',
f'- Offline Streamlit component exceptions: {len(ui.get("exceptions",[])) if ui else "not run"}; context reset: {ui.get("context_reset","not run")}; editable draft: {ui.get("draft_editor_present","not run")}; no Send button: {ui.get("no_send_button","not run")}. These are mocked component checks, not model/browser results.',
'- Real-data tool tests exercise exact schedules, missing courses/contacts, verified contacts, conflicting slots, incomplete counts, overlap comparison and Chroma/BM25 retrieval.',
'- The original-source SHA-256 audit is in scripts/verify_originals.py and its build output.','',
'| Real ADK smoke file | Recorded cases | Passed conditions | Median latency (s) |','|---|---:|---:|---:|']
for name,n,ok,latency in smokes:rows.append(f'| {name} | {n} | {ok} | {latency} |')
if not smokes:rows.append('| No real ADK smoke completed yet | 0 | 0 | not_run |')
rows+=['','Smoke artifacts record real schedule, document retrieval, draft and compound requests. A focused `--failed-only` recheck may retain prior passing cases; those records contain an audit pointer and are not counted as new inference runs. Raw attempts, including failures, remain in the private smoke history.','']
regressions=[load(path,{}) for path in sorted(private.glob('course-regression-*.json'))]
if regressions:
    rows+=['','The prerequisite regression checks that the actual answer includes the complete explicit prerequisite field from a returned source, rather than only unrelated course text. Expected fields are derived at runtime and retained privately.','',
        '| Screenshot regression | Passed | Latency (s) |','|---|---|---:|']
    for result in regressions:rows.append(f'| {result["model"]} / {result["mode"]} | {result["passed"]} | {result["response"]["metrics"]["latency_s"]} |')
rows+=['','## Evaluation execution','',
'The private frozen set has 30 prompts with source excerpts/record candidates, requirements and expected statuses. Gold answers are builder-derived candidates; human adjudication is pending. Q28 uses the actual supplied timetable/offering conflict instead of inventing conflicting attendance policies. Separate development prompts are excluded from the frozen test set.','',
f'- Matrix: 2 modes × 2 models × 30 prompts × 3 seeds = 360 planned trials. Latest saved pilot: {raw_files[-1].name if raw_files else "none"}; state: {run_state.get("state","not_run")}; recorded rows: {len(runs)}; unexecuted in that pilot: {360-len(runs)}.',
'- The interrupted development pilots used an earlier runtime/configuration and do not establish a completed final evaluation. The full 360-trial comparison and human adjudication remain pending.',
'- Requested controls: temperature 0.2, seeds 11/22/33, 4096 context tokens, bounded output, no answer cache and fresh sessions. Seed reproducibility is not guaranteed by the runtime.',
'- Raw responses, returned evidence, tool traces, model digests, latencies and sampled system RAM are retained locally. Preflight scope/evidence guards legitimately execute zero LLM calls; this is visible in each trace.','',
'| Model / mode | Trials | Status matches (not accuracy) | Runtime errors | Median latency (s) | p95 latency (s) |','|---|---:|---:|---:|---:|---:|']
for model in ('qwen3:8b','llama3.1:8b'):
    for mode in ('single','multi'):
        group=[r for r in runs if r['model']==model and r['mode']==mode]
        times=sorted(r['latency_s'] for r in group)
        rows.append(f'| {model} / {mode} | {len(group)} | {sum(r["status_match"] for r in group)} | {sum(r["status"]=="error" for r in group)} | {round(statistics.median(times),3) if times else "not_run"} | {round(times[max(0,int(len(times)*.95)-1)],3) if times else "not_run"} |')
if runs:rows+=['',f'Peak sampled total system RAM during trials: {max(r["peak_system_ram_bytes"] for r in runs)/2**30:.2f} GiB. This includes the OS and other applications; it is not isolated model RSS.']
rows+=['','Factual accuracy, groundedness, citation precision/coverage, refusal correctness, retrieval recall and substantive changed-answer rate require the accompanying human scoring sheet and rubric. They are **unverified**, not assumed to meet the design targets. Status matching and a valid citation ID do not prove correctness. No multiagent benefit is claimed before reviewing actual trials and their latency.','',
'## Remaining limits and human review','',
'- Confirm the exact programme/branch and curriculum/cohort applicability. The setup programme field contained a student name.',
'- Supply/verify current attendance and examination-policy amendments before relying on those current rules. Older regulations remain contextual evidence rather than a verified current replacement.',
'- Confirm complete department lists and explicit course levels/categories before exact elective counts. No complete 400-level Humanities count has been asserted.',
'- Resolve the documented cross-source slot conflict; do not choose a source merely because its filename sounds newer.',
'- Some instructor contacts are absent and remain explicit unknown placeholders. Clock text without a unique AM/PM interpretation may require clarification.',
'- Optional Google OAuth sync is not implemented; manual import is the supported, required route.',
'- Automated browser opening/visual inspection was blocked when the browser permission gate declined the local origin. The native UI service and offline component tests are separate checks. Open the local URL manually.',
'- No retrieval confidence threshold is claimed to be empirically tuned; hybrid rankings select candidates and conservative evidence gates decide whether to answer. Human semantic review remains necessary.','',
'## Reproduction and submission','',
'Use README.md for setup, launch, import/review, tests, model recovery and full evaluation commands. Run the model/data checks from the project virtual environment. Resume a matching interrupted matrix with `python -m helpdesk evaluate --dataset real --resume evaluation/results/real/<run>.jsonl`; the harness rejects changed questions/index/settings. Private source submission must be arranged separately from Git.','']
(ROOT/'report/FINDINGS.md').write_text('\n'.join(rows),encoding='utf-8')
print(ROOT/'report/FINDINGS.md')
