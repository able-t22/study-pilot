# StudyPilot — Evaluation & Benchmarking

Reproduce: `python run.py` → Evaluation tab, or `python scripts/run_eval.py`. Results are written to `data/eval/`.

## Answer quality
Test set: auto-built from the ingested course. In-scope questions have known source units (LLM-phrased when a provider is configured); 12 off-material queries test refusal. Add your own cases in `data/eval/custom_testset.json`.

| Metric | Offline run on sample course |
|---|---|
| Faithfulness | 1.00 (lexical proxy) |
| Answer relevancy | 0.47 |
| Context precision | 0.93 |
| Context recall | 1.00 |
| In-scope answer rate | 1.00 |
| Correct refusal (off-material) | 0.92 |

**Honesty note.** The offline run uses keyword-style questions and lexical proxies, so faithfulness and recall are optimistic. For submission, set `LLM_PROVIDER`, upload real course material (e.g. an NPTEL/MIT OCW lecture, slides, textbook chapter) and re-run to get LLM-judged numbers.

## Personalisation (simulated students)
30 synthetic students (novice / mixed / advanced) × 6 sessions × 12 questions. Baseline = random topic and question, no novelty filter.

| | Adaptive (ours) | Random baseline |
|---|---|---|
| Mean mastery gain | +42.2 pts | +38.3 pts |
| Repetition rate | 21.1 % | 39.6 % |

Adaptive wins on 100 % of paired students. **Caveat:** the simulator's learning model penalises repeats and rewards prerequisite order, which favours our policy by construction; it demonstrates mechanics, not real-world gains. A real pilot with human learners is the next step.


---
# Evaluation report (v3): framework, test set, personalization study

## How to run
| What | Where | Command |
|---|---|---|
| RAG pipeline on the team test set (native RAGAS-definition metrics) | Evaluation tab -> *Check answer quality* | `POST /api/eval/rag?n=20` |
| Same pipeline with **DeepEval** (FaithfulnessMetric, AnswerRelevancyMetric, ContextualPrecisionMetric, ContextualRecallMetric) | Evaluation tab -> *Run DeepEval* | `pip install -r requirements-eval.txt`, needs `OPENROUTER_API_KEY` (OpenRouter judge) |
| KB integrity + question/tag/answer-key audit + learner-model calibration | Evaluation tab -> *Audit questions & tags* | `POST /api/eval/audit` |
| Multi-session simulated students | Evaluation tab -> *Run simulated-student study* | `POST /api/eval/sim?students=30` |
| Offline regression of all of the above | | `python scripts/test_requirements.py`, `python scripts/test_deepeval_wiring.py` |

## Team test set (`tests/testset_intro_ml.json`)
20 hand-written questions for the bundled sample course, each with the **exact source locations** that answer it (textbook page, slide number, lecture time), plus
6 *adjacent* off-material questions (real ML topics the course does not cover: attention, Adam, SVM, dropout, RL, vanishing gradients) as hard refusal cases.
Truth is resolved to knowledge-base units at run time, so it survives re-ingestion. To test another course, add `data/eval/custom_testset.json`-style items or copy the file's schema.

## Metrics, as measured here (offline mode, no AI key, sample course)
| Metric | Team set | Notes |
|---|---|---|
| Faithfulness | 1.00 | lexical proxy; extractive answers are quoted from context, so this is optimistic |
| Answer relevancy | 0.32 | lexical proxy (low because extractive answers are long); LLM-judged with a key |
| Context precision | 0.94 | relevant chunks ranked first (ground-truth locations) |
| Context recall | 1.00 | right source retrieved (same page / slide / video within 60 s) |
| Hit@1 / MRR | 0.95 / 0.975 | |
| Citation accuracy | 0.55 | **weak**: answers cite several units and only about half match the labelled location |
| Reference recall | 0.95 | RAGAS-style: reference answer attributable to retrieved context |
| Off-material declined (adjacent) | 0.67 (4/6) | **weak**: 2 of 6 adjacent ML questions (e.g. regularisation-like) were answered from loosely related material |

Offline numbers are a floor for retrieval and an optimistic ceiling for generation. Re-run with a key for LLM-judged generation metrics, and with DeepEval for an independent framework.
`scripts/test_deepeval_wiring.py` proves the DeepEval metrics execute on the real pipeline output using a *stub* judge (its 1.0 scores are meaningless); I could not run DeepEval against a live judge in the build environment.

## Personalization study (18 synthetic students x 6 sessions, extractive question pool)
| Result | Adaptive | Adaptive + intake | Random baseline |
|---|---|---|---|
| Mean mastery gain (true mastery, points) | 38.7 | 38.8 | 35.1 (adaptive +10% relative) |
| Question repetition rate | 32% | | 50% |
| Learner-model error vs a never-learning prior-only model | -3% after diagnostic -> **+50%** by last session | | |
| Share of questions aimed at the truly weakest third | 26% -> 33% | | 29% (random) |
| Error right after diagnostic (MAE) | 0.233 | **0.185** | |

Reading it honestly: the measurable gains are mastery (+10% vs random), far less repetition, an estimate that becomes much better than a non-personalised one as data accumulates, and a better cold start with the intake prior (-21% error). Weak spots: targeting is only slightly better than random (33% vs 29%) because the learner model has few observations per topic; raw error vs truth and rank correlation do **not** improve (rank correlation even falls) because adaptive practice itself changes true mastery, which confounds those two metrics, which is why the prior-only comparison is the headline. Students and their learning are simulated (see `assumptions` in the result JSON); the study shows the system behaves sensibly, not that real learners gain this much.

## Question & tag quality
`audit.question_audit()` checks: share verified, answer key supported by its source unit, MCQ well-formedness (one key, distinct options), topic tag vs retrieval of the stem (top-1/top-3), source unit in top-5, observed correct rate by difficulty tag (monotonic?), and a learner-model replay over real attempts (Brier vs base rate, calibration bins).
On the sample course: 95% verified, 100% keys found in source, 100% topic-tag agreement (top-3), 100% source-in-top-5. The learner-model replay needs real answers: scripted test answers are not a learner, so ignore its Brier there; with real use, skill score > 0 means better than a constant guess.

## Limits
Retrieval is lexical TF-IDF by default (neural embeddings optional); judge and generator share a model family with OpenRouter self-consistency verification; tag-accuracy checks are proxies, not human grading; synthetic-student results are indicative only; audio briefs use the browser's speech synthesis (script download provided), not a generated audio file.
