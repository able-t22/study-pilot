# StudyPilot

A source-grounded study companion that turns your course material into cited answers, adaptive practice and a personal revision workflow.

## Run locally

Requires Python 3.10–3.12.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Add OPENROUTER_API_KEY to .env
python run.py
```

Open http://127.0.0.1:8000. If an existing virtual environment reports that its Python executable is missing, install Python again and recreate the environment.







## Uploads

Create a learner, then add PDFs, PPTX slides, text, Markdown, VTT/SRT transcripts, audio or video.

- **Fast upload is on by default.** It extracts readable text, performs OCR on scanned pages and builds topics locally. It skips AI figure descriptions, video frames and LibreOffice slide rendering.
- Turn off Fast upload before adding a file for full visual processing and AI topic naming. Re-analyse updates topic structure; it does not re-extract skipped figures from existing files.
- Unit inserts and topic tags are batched to reduce database round trips. Disk copying runs in a worker, keeping the server responsive.
- Each upload batch has its own directory, so repeated filenames cannot overwrite a previous source. Unsupported, empty and duplicate-name files are rejected.
- A matching VTT/SRT uploaded with a video or audio file avoids transcription. The sidecar is consumed once rather than ingested twice.
- Speech transcription is local. The first media upload may download the Whisper model. Set WHISPER_MODEL=tiny for faster transcription, or upload a transcript instead.

**Adding material or re-analysing rebuilds topics and resets quiz history and mastery.** Upload the course material before starting practice. Full visual processing, OCR and long recordings can still take time.

## Study workflow

| Tool | What it does |
| --- | --- |
| Study cockpit | A daily recall → repair → apply mission, exam countdown, goal, review counts and mastery based on observed topics |
| Mistake notebook | Latest incorrect answers with explanations and exact source links; correct retries clear mistakes; downloadable Markdown |
| Source search | Search all uploaded material and jump to matching pages, slides or timestamps without AI calls |
| Tutor | Grounded answers with citations, explanation styles and English, Hindi, Tamil or Malayalam support |
| Practice | Adaptive, custom, diagnostic and mock-exam questions, background generation progress, verification and cited feedback |
| Notes | Custom style, length, language and focus; copy, print or download Markdown |
| Course map | Topics, concepts and prerequisite relationships with mastery |
| Revise | Spaced repetition, Anki export, flashcards, slide decks, audio scripts, glossary and teach-back |
| Dashboard | Learner mastery, forgetting estimates, trajectory, assessment reports and study schedule |
| Evaluation | Retrieval/answer quality, question/tag audit and simulated study; optional DeepEval |

The cockpit's mastery estimate is not an exam-score prediction. Untouched topics are excluded from its average. Audio uses browser speech synthesis; it is not a rendered audio recording.

Quiz generation and batch review share a QUIZ_AI_SECONDS budget (25 seconds by default). A quiz uses at most one generation batch and one review batch; model failover may add HTTP attempts within that budget. Existing question-bank items and local concept/formula questions fill the remaining places. Quiz generation uses an object containing a questions list, compatible with JSON-object mode. Empty or invalid scopes return a useful error. If AI output is unusable, source-based concept questions keep practice available and are clearly labelled. A smaller supported quiz may be returned with a notice. Mistake retries use existing questions and need no AI generation.

Learners have separate databases, uploads and study state. The local profile cookie selects a workspace; this is not a production authentication system.

## Database and deployment

SQLite is the default. For Supabase/Postgres, set DATABASE_URL to your database connection string (session pooler recommended), then run python scripts/check_db.py. Each learner uses a separate database schema; keep the connection string secret. See supabase/schema.sql.

Uploaded files remain on disk. A deployment needs persistent storage. Optional Docker:

```bash
docker build -t studypilot .
docker run -p 8000:8000 --env-file .env -v sp_data:/data studypilot
```

Optional neural embeddings: install requirements-extra.txt and set EMBEDDINGS=1. Optional evaluation dependencies: requirements-eval.txt. LibreOffice improves exact slide previews in full ingestion mode.

## Verification

```bash
python scripts/selftest.py
python scripts/test_llm_fallback.py
python scripts/test_features.py
python scripts/test_repairs.py
```

Tests use temporary workspaces and mocked provider responses; they do not validate live model availability, credits or real API latency. The repair suite covers fast uploads, source search, empty-course errors, question jobs, mistake repair, filename isolation and job ownership.

Architecture: app/ingest.py → app/kb.py → app/retrieval.py → tutor, assessments and revision. FastAPI serves the vanilla JavaScript interface in static/. No training is required.

### Study-flow repairs

All seven note styles are selectable without resetting source or focus controls. Notes, tutor answers, questions and revision use local MathML rendering for common TeX formulas. Revision packs load automatically from source passages, even when every topic is strong or the AI provider is unavailable. The Revision and Evaluation panels remain inside the main layout.

The sidebar reports configuration and actual provider connection state separately. Open its arrow button to test OpenRouter and see specific authentication, quota, model or network errors. A failed tutor request displays clearly labelled source excerpts rather than claiming they are a reasoned AI answer.

See [HOW_TO_RUN.md](HOW_TO_RUN.md) for startup and troubleshooting. Run `python scripts/test_study_flow.py` for the new outage, request-count, revision, mathematics and concurrent-startup regressions.
