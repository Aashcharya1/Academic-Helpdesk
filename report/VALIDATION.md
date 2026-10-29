# Initial validation notes (historical)

These notes capture the early setup state. See FINDINGS.md for the current, generated execution record. The pending list below is historical, not the final delivery status.

The original technical design was read in full. The supplied folder contains 28 academic files, 26 distinct SHA-256 hashes. Two duplicate pairs are the 2019 regulation PDFs and the two copies of Circular 2283. The programme field in setup notes contains a student name; no exact programme has been inferred. Python 3.12.1, Git 2.56.0 and Ollama 0.40.13 were detected on native Windows. Approximately 15.4 GiB usable RAM and 217 GiB free on F: were observed at setup. These are observations, not peak application measurements.

Implemented code includes native Windows launchers; PDF/OCR, DOCX, workbook, CSV, text/HTML and EML-body extraction; immutable originals and private working snapshots; manual metadata and table review; Chroma with explicitly supplied Ollama embeddings; BM25/dense reciprocal-rank fusion; exact timetable/instructor/count tools; two ADK agent configurations; bounded execution; source-ID and quote validation; draft-only emails; redacted SQLite unresolved queue; local Streamlit chat and admin UI; and a 360-trial experiment harness.

Pending validation at this revision: completed dependency installation, source ingestion/OCR review, model downloads and inference, real ADK tool execution, activated Chroma index, automated tests, browser launch/inspection and evaluation trials. No accuracy, groundedness, latency or stability findings are reported before real execution.

Known corpus review needs include current attendance/examination amendments, exact student programme/curriculum applicability, complete explicit Humanities course-level classifications and instructor-email coverage. Missing evidence must produce a logged refusal or a marked draft placeholder. An older base regulation is not silently promoted to a verified current policy.

Evaluation gold is builder-derived candidate evidence. Final human adjudication and human semantic scoring remain explicitly pending even after automated trial execution. The conflict attendance test is labelled as unconfirmed-amendment evidence limitation; no fake policy conflict has been added to real data. Optional OAuth synchronization is not implemented because the design's required acquisition path is manual local import.
