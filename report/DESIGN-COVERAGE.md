# DESIGN coverage and acceptance checks

This maps the supplied design to implementation. Execution results are reported separately in FINDINGS.md and its raw evidence files.

| Design area | Implementation | Verification / limit |
|---|---|---|
| Local Windows runtime, project dependencies, F: model store | `Setup.ps1`, `Start.ps1`, `helpdesk/doctor.py` | Doctor API/inference output; persistent user environment and manifest matching |
| 20–30 distinct real sources | Private import manifest and SHA-256 audit | 28 supplied files, 26 distinct hashes; builder approved 24; final human authority/applicability review pending |
| Manual imports and OCR | `helpdesk/importers/` | PDF/DOCX/XLSX/CSV/HTML/TXT/EML, attachments, all tabs, local OCR; originals retained |
| Preview, mapping, approval and safe activation | Import & review page; `editable_candidate`, `build_index` | Review edits use a detached candidate; activation follows successful indexing |
| Metadata and source provenance | Snapshot manifest, working units, chunks and structured CSVs | Stable source/version/row IDs; unknown completeness/levels remain unknown |
| Embeddings and retrieval | `helpdesk/rag/` | Actual EmbeddingGemma vectors in Chroma; BM25 + reciprocal-rank fusion; scores retained; no web fallback |
| Schedule, counts, contacts and overlaps | `helpdesk/tools/` | Exact records; duplicate codes counted once; incomplete counts refuse; unresolved conflicts require clarification |
| Single-agent baseline | `helpdesk/agents/` | ADK LlmAgent with all approved tools |
| Orchestrator and three specialists | `helpdesk/agents/` | ADK AgentTool wrappers; serialized specialist calls; shared local model and common data tools |
| Memory, bounds and privacy | Service, Budget, SQLite and filesystem inference lock | Six data calls, three specialist calls, ten LLM generations; timeout; minimal sessions; redacted queue |
| Evidence and refusals | `helpdesk/service.py` | Returned-source IDs and quoted text checked; exact table values rendered by backend; missing facts are not invented |
| Review-only drafts | Draft tool and UI editor | Verified recipient or placeholder, dates/identity placeholders, supplied facts only; no send API |
| UI | `app/main.py`, `app/styles.css` | Black/grey chat, installed Segoe UI font, pinned composer, native chat scrolling, collapsed source cards; five separate pages, REAL/DEMO and context reset |
| Experiments | Evaluation modules and matrix | 30 frozen prompts, 3 seeds, 2 models, 2 modes; actual executions only, raw traces, timing, RAM and changes |
| Human metrics | Scoring CSV and `helpdesk.evaluation_metrics` | Accuracy/groundedness/citation scores stay null until required human scores exist |
| Reproducible submission | README, pinned lock, reports, archive builder | Private data excluded from Git; local archives separately labelled |

## Documented implementation choices

- Python 3.12 uses the user's installed native runtime; the design's Python 3.11 preference did not require an additional runtime. Tested package versions are pinned.
- The laptop has 16 GB nominal RAM and a 4 GB GPU. Chat uses six CPU threads after cold GPU initialization failures; embeddings use four CPU threads. One chat model runs at a time. The native prompt cache is capped at 512 MiB. Actual total system RAM and latency are measured, rather than inferred from design estimates.
- Structured tool results and drafts can use ADK's `skip_summarization` facility. The model still chooses and calls tools; the backend renders exact values. Root orchestration remains active for compound requests. Explicit backend finalizations appear in traces and must not be counted as extra model generations.
- Citation validation normalizes punctuation/spacing. If a quote points at the wrong returned source but exactly matches another returned source, its pointer can be repaired. Invented IDs and unsupported quotes fail validation. Semantic relevance still requires human review.
- Q28 uses a real conflict between supplied timetable/offering rows instead of inventing contradictory attendance policies. Q14 includes the preceding count question as session setup, recorded separately from the 360 scored trials.
- Current attendance/exam amendments, exact programme/cohort applicability and complete explicit Humanities classifications are unavailable or unverified. These remain honest refusals/clarifications.
- Optional Google OAuth sync is omitted; the required manual-import workflow is implemented.

## Manual review before submission

Confirm the exact programme and cohort, approve source authority/applicability, review the candidate gold answers and score semantic support. Check the actual browser layout and complete a fresh chat/draft demonstration. Browser visual inspection was blocked by the local-origin permission gate during development; mocked Streamlit component checks are identified separately from real model checks. No account credentials are needed for the local manual-import workflow.
