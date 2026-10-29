# Submission guide

Open `http://127.0.0.1:8501` after running `Start.cmd` from this folder. The selected model/mode must pass the real integration checks before chat is enabled. Read `report/FINDINGS.md` for measured completion status; a feature's presence is not proof that every model answer is correct.

## Files to review

| Deliverable | Location |
|---|---|
| Application and genuine ADK agents | `app/`, `helpdesk/` |
| Windows launcher and setup | `Start.cmd`, `Start.ps1`, `Setup.ps1` |
| Resolved dependencies | `requirements.lock` |
| Reproduction and troubleshooting | `README.md` |
| Design coverage and manual checks | `report/DESIGN-COVERAGE.md` |
| Measured findings | `report/FINDINGS.md` |
| Frozen 30 prompts and candidate expected evidence | `evaluation/questions.jsonl` |
| Matrix, raw outputs, metrics and repeated-run comparisons | `evaluation/matrix.yaml`, `evaluation/results/real/` |
| Human adjudication sheet | `evaluation/results/real/*.human-scoring.csv` |
| Source exports, hashes and reviewed extraction | `data/private_import/`, active `data/real/snapshots/` |

`python scripts/build_submission.py` creates two verified local archives under `submission/`. The code archive excludes private material, environments, caches and model weights. The separately labelled private-evidence archive contains supplied source exports, expected evidence and measured outputs; review it and share only through the permitted assignment submission channel. Neither archive is uploaded automatically. Private content is excluded from Git.

The source archive is evidence for review, not a portable prebuilt Chroma database. On another computer, follow README setup, import/review the supplied exports and rebuild embeddings. Preserve the local full project for the working demonstration.

## Short demonstration

1. Show REAL dataset, approved-source count, active term and installed models.
2. Ask a course-content question and open its supporting source excerpt.
3. Ask the slot of Autonomous Systems; inspect the exact worksheet citation.
4. Ask a deliberately unavailable course or unverified elective count; show the refusal and human review queue.
5. Draft academic leave; edit the recipient, subject and body and download it. There is no sending capability.
6. Switch baseline/multiagent modes and compare the actual tool traces and measured latency.
7. Show raw experiments and changed-output comparisons. Explain unscored human metrics and documented source gaps accurately.

Full marks cannot be guaranteed by a software build. The design explicitly requires human gold-answer review, source/applicability confirmation and an honest findings report. Do not present unexecuted trials, provisional gold or unscored accuracy as verified achievements.
