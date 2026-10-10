# StudyPilot — Architecture, Grounding & Learner Model
(Project documentation)

## 1. System overview
```
PDF / PPTX / video / audio / VTT / SRT
        │  ingest.py   (PyMuPDF + OCR fallback · python-pptx · faster-whisper · keyframes → vision LLM / OCR)
        ▼
 units: text | figure | transcript   each with  loc = {page} | {slide} | {t0,t1}  + label + source_id
        │  kb.py       (TF-IDF + LSA clustering → LLM naming → subtopics, concepts → prerequisite DAG → tag every unit)
        ▼
 SQLite or Supabase/Postgres (db.py): sources, units, topics, concepts, prereqs, questions, assessments, attempts, mastery, mastery_log
        │
 retrieval.py  BM25 + TF-IDF(1–2 gram) [+ MiniLM] → Reciprocal Rank Fusion
   ├── tutor.py     grounded Q&A, coverage gate, [S#] citations, refusal / flagged outside knowledge, Hindi
   ├── assess.py    generate → verify → de-duplicate → grade → cited feedback → report
   ├── revision.py  flashcards, audio briefs, schedule inputs
   └── learner.py   BKT + forgetting curve + adaptive policy + planner + mastery trajectory
 evals.py (answer quality) · simulate.py (synthetic students)      main.py (FastAPI)  ↔  static/ (dashboard)
```

## 2. Multimodal ingestion (Req. 1)
| Input | Method | Origin link |
|---|---|---|
| PDF textbook | PyMuPDF text blocks; OCR fallback for scans; embedded + vector figures rendered | `page` |
| PPTX | text, tables, speaker notes, pictures | `slide` |
| Video / audio | faster-whisper transcription (or `.vtt/.srt` sidecar); keyframes every `FRAME_EVERY` s | `t0–t1` seconds |
| Figures | vision LLM caption (OpenRouter vision model) or OCR of labels → stored as citable `figure` units | same as parent |

Structure: units are clustered into topics, split into subtopics, key concepts are extracted, and a prerequisite DAG is inferred (ordering + LLM). Every unit stores `topic_id`, `subtopic_id`, `concept_ids` and its `loc`.

## 3. Grounding method (Req. 2)
1. Hybrid retrieval (BM25 + TF-IDF, fused by RRF) returns numbered context blocks.
2. **Coverage gate** before generation: query content-term coverage + score floor. Below threshold → refuse.
3. The generator may use only the numbered blocks and must cite `[S#]` after each claim; the model can also return `covered:false`.
4. Citation chips resolve to `source_id + loc` and open the exact PDF page (with highlight), slide, or video at the timestamp.
5. Outside knowledge is shown only if the learner toggles it, in a separate amber box labelled *not source-backed*.

## 4. Assessment pipeline (Req. 3)
Allocation (adaptive policy or chosen scope) → per-topic generation of MCQ / short / numerical questions from cited units → **verification** (independent re-solve by a verifier model; OpenRouter self-consistency verification; safe numeric `calc` check; extractive check offline) → **novelty filter** (TF-IDF near-duplicate vs the learner's history and the current batch) → grading with cited feedback and a misconception hint → report (weak topics, misconceptions, mastery before/after, recommendations, printable HTML at `/api/report/{id}`).
Each question carries topic, source unit/location, difficulty, `verified` flag and note.

## 5. Learner model (Req. 4)
Per student × topic:
- **BKT**: `P(know)` updated with guess `{mcq .25, short .08, numerical .03}` and slip `{easy .05, medium .10, hard .18}`, learn rate 0.15.
- **Forgetting curve**: stability `S` (days) ×1.8 on success, ×0.5 on failure; retrievability `R = exp(−Δt/S)`; effective mastery `P·(0.5+0.5R)`; belief decays by `0.7+0.3R` before each update.
- **Chat evidence**: confusion / understanding phrases (English + Hindi) update with weight 0.3.
- **Cold start**: intake (level, goal, exam date) sets the prior (0.15 / 0.35 / 0.60); a diagnostic quiz covers every topic.
- **Policy**: weakest topics first with diminishing returns, prerequisites unlocked before dependants, difficulty from mastery.
- **Trajectory**: every update is logged (`mastery_log`) and plotted on the dashboard, making personalisation visible per answer.
- **Planner**: day-by-day simulation of the forgetting curve to the exam date; final day is a mock exam.

## 6. Evaluation (Req. 5)
See `docs/EVALUATION.md`. Answer-quality metrics are implemented natively (`app/evals.py`); the simulated-student study is `app/simulate.py`.

## 7. Design decisions
- Pretrained models only; zero training, so the whole system runs on a laptop.
- Offline mode keeps the product demonstrable without keys; the UI states which mode is active.
- SQLite + FastAPI + vanilla JS: one process, no build step, easy to review.

## Per-learner workspaces
`app/config.py` resolves `DB_PATH / UPLOADS / MEDIA / EVAL` from a context variable set on every request from the `sp_user` cookie, so each learner has an isolated SQLite DB, upload folder, media folder and evaluation folder under `data/users/<id>/`. Background jobs copy the context, so ingestion and generation always run in the right workspace.

## Notes generator (`app/notes.py`)
Segments (transcript windows, PDF pages, slides, on-screen figure descriptions) are chunked and sent with the learner's options (style, length, level, language, free-text focus). Chunk outputs carry `[[U<unit_id>]]` markers that the UI turns into clickable timestamp/page citations. Offline mode uses TF-IDF sentence scoring with focus-term boosting.
