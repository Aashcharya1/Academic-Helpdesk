# Academic Helpdesk: implementation and measured validation

The application runs locally at http://127.0.0.1:8501. Original academic exports remain private and unchanged. This report distinguishes executed checks from pending model trials and human review.

## Environment

- Python: 3.12.1 (tags/v3.12.1:2305ca5, Dec  7 2023, 22:03:25) [MSC v.1937 64 bit (AMD64)].
- Platform: Windows-11-10.0.26300-SP0.
- Persistent user OLLAMA_MODELS: F:\Ollama\models.
- Dependencies are installed in the project virtual environment and pinned in requirements.lock. pip check was executed separately; see setup logs.
- Model transfers use official Ollama manifests and complete SHA-256 checks; interrupted small ranges are retained in the project cache.

Chat currently uses six CPU threads (`num_gpu=0`) after native GPU cold-start failures on the 4 GB laptop GPU. Embeddings use four CPU threads. The host prompt cache is capped at 512 MiB. The requested 8B models have not been substituted.

| Requested model | Downloaded size (GB) | API availability | Quantization | Actual inference |
|---|---:|---|---|---|
| qwen3:8b | 5.23 | available | Q4_K_M | tool call verified |
| embeddinggemma:300m | 0.62 | available | BF16 | embedding probe: 768 dimensions |
| llama3.1:8b | 4.92 | available | Q4_K_M | tool call verified |

## Corpus and application

- The UI uses plain black/grey, installed Segoe UI fonts, a pinned bottom composer, native follow-output scrolling and a narrow reading column. Source cards and response details are collapsed. Administration is separated into sidebar pages.
- Supplied files: 28; distinct hashes: 26; approved for retrieval by builder review: 24. Final human applicability review remains separate.
- Indexed chunks: 1733. Real embeddings and hybrid retrieval data smoke check: True.
- All workbook tabs are extracted. Structured records retain source document/hash, worksheet and row/cell locator. Missing values are blank/unknown; a code digit is never used to infer course level.
- Scanned pages use cached local OCR assets. Corrected English transcriptions retain the raw OCR working text and original PDFs.
- EML bodies and attachments, PDF, DOCX, XLSX/CSV and HTML/TXT loaders are implemented. Custom workbook column mapping is available in the local review UI.
- Baseline: one ADK LlmAgent with approved tools. Multiagent: root plus policy, schedule and email AgentTool specialists, with shared model and bounded sequential execution.
- Backends validate returned evidence IDs/quotes, snapshot fingerprints, unresolved-source conflicts and request budgets. Factual output uses source excerpts and deterministic structured values. Semantic relevance is not established by ID validation alone.
- Email is editable draft-only. Unknown contacts and identity/dates remain placeholders; multiple instructors require recipient review. No sending API or Send button exists.
- REAL and DEMO use separate snapshots, indexes, state and results. Context changes clear chat/course context. No silent fallback or chat web search exists.

## Executed checks

- Automated backend/loader/contract tests: 29 passed.
- Offline Streamlit component exceptions: 0; context reset: True; editable draft: True; no Send button: True. These are mocked component checks, not model/browser results.
- Real-data tool tests exercise exact schedules, missing courses/contacts, verified contacts, conflicting slots, incomplete counts, overlap comparison and Chroma/BM25 retrieval.
- The original-source SHA-256 audit is in scripts/verify_originals.py and its build output.

| Real ADK smoke file | Recorded cases | Passed conditions | Median latency (s) |
|---|---:|---:|---:|
| smoke-llama3.1-8b-multi.json | 4 | 4 | 48.93 |
| smoke-llama3.1-8b-single.json | 4 | 4 | 32.62 |
| smoke-qwen3-8b-multi.json | 4 | 4 | 54.78 |
| smoke-qwen3-8b-single.json | 4 | 4 | 45.52 |

Smoke artifacts record real schedule, document retrieval, draft and compound requests. A focused `--failed-only` recheck may retain prior passing cases; those records contain an audit pointer and are not counted as new inference runs. Raw attempts, including failures, remain in the private smoke history.


The prerequisite regression checks that the actual answer includes the complete explicit prerequisite field from a returned source, rather than only unrelated course text. Expected fields are derived at runtime and retained privately.

| Screenshot regression | Passed | Latency (s) |
|---|---|---:|
| llama3.1:8b / multi | True | 48.875 |
| qwen3:8b / multi | True | 101.187 |

## Evaluation execution

The private frozen set has 30 prompts with source excerpts/record candidates, requirements and expected statuses. Gold answers are builder-derived candidates; human adjudication is pending. Q28 uses the actual supplied timetable/offering conflict instead of inventing conflicting attendance policies. Separate development prompts are excluded from the frozen test set.

- Matrix: 2 modes × 2 models × 30 prompts × 3 seeds = 360 planned trials. Latest saved pilot: 20261029T195425.jsonl; state: aborted_diagnostic; recorded rows: 8; unexecuted in that pilot: 352.
- The interrupted development pilots used an earlier runtime/configuration and do not establish a completed final evaluation. The full 360-trial comparison and human adjudication remain pending.
- Requested controls: temperature 0.2, seeds 11/22/33, 4096 context tokens, bounded output, no answer cache and fresh sessions. Seed reproducibility is not guaranteed by the runtime.
- Raw responses, returned evidence, tool traces, model digests, latencies and sampled system RAM are retained locally. Preflight scope/evidence guards legitimately execute zero LLM calls; this is visible in each trace.

| Model / mode | Trials | Status matches (not accuracy) | Runtime errors | Median latency (s) | p95 latency (s) |
|---|---:|---:|---:|---:|---:|
| qwen3:8b / single | 8 | 7 | 1 | 0.024 | 42.641 |
| qwen3:8b / multi | 0 | 0 | 0 | not_run | not_run |
| llama3.1:8b / single | 0 | 0 | 0 | not_run | not_run |
| llama3.1:8b / multi | 0 | 0 | 0 | not_run | not_run |

Peak sampled total system RAM during trials: 14.12 GiB. This includes the OS and other applications; it is not isolated model RSS.

Factual accuracy, groundedness, citation precision/coverage, refusal correctness, retrieval recall and substantive changed-answer rate require the accompanying human scoring sheet and rubric. They are **unverified**, not assumed to meet the design targets. Status matching and a valid citation ID do not prove correctness. No multiagent benefit is claimed before reviewing actual trials and their latency.

## Remaining limits and human review

- Confirm the exact programme/branch and curriculum/cohort applicability. The setup programme field contained a student name.
- Supply/verify current attendance and examination-policy amendments before relying on those current rules. Older regulations remain contextual evidence rather than a verified current replacement.
- Confirm complete department lists and explicit course levels/categories before exact elective counts. No complete 400-level Humanities count has been asserted.
- Resolve the documented cross-source slot conflict; do not choose a source merely because its filename sounds newer.
- Some instructor contacts are absent and remain explicit unknown placeholders. Clock text without a unique AM/PM interpretation may require clarification.
- Optional Google OAuth sync is not implemented; manual import is the supported, required route.
- Automated browser opening/visual inspection was blocked when the browser permission gate declined the local origin. The native UI service and offline component tests are separate checks. Open the local URL manually.
- No retrieval confidence threshold is claimed to be empirically tuned; hybrid rankings select candidates and conservative evidence gates decide whether to answer. Human semantic review remains necessary.

## Reproduction and submission

Use README.md for setup, launch, import/review, tests, model recovery and full evaluation commands. Run the model/data checks from the project virtual environment. Resume a matching interrupted matrix with `python -m helpdesk evaluate --dataset real --resume evaluation/results/real/<run>.jsonl`; the harness rejects changed questions/index/settings. Private source submission must be arranged separately from Git.
