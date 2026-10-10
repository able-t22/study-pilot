"""Pipeline evaluation with an established framework: DeepEval (pip install deepeval).
Metrics: FaithfulnessMetric, AnswerRelevancyMetric, ContextualPrecisionMetric, ContextualRecallMetric.
The LLM-as-judge is StudyPilot's own LLM layer (OpenRouter) wrapped as a DeepEval custom model, so no extra key is needed.
Runs the real tutor pipeline (retrieval + grounded answer) on the team test set; off-material queries are scored separately as refusal accuracy."""
import json, os, re, time
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")   # no data leaves the machine except the judge calls to your own LLM provider
import numpy as np
from . import llm, evals, config as C
from .retrieval import get_index
from .tutor import answer

METRICS = {"faithfulness": "FaithfulnessMetric", "answer_relevancy": "AnswerRelevancyMetric",
           "context_precision": "ContextualPrecisionMetric", "context_recall": "ContextualRecallMetric"}


def make_judge():
    from deepeval.models import DeepEvalBaseLLM

    class StudyPilotJudge(DeepEvalBaseLLM):
        def __init__(self): super().__init__(model="studypilot-llm-layer")
        def load_model(self): return self
        def get_model_name(self): return "StudyPilot LLM layer (OpenRouter)"
        def generate(self, prompt, schema=None, **kw):
            if schema is None: return llm.chat("You are a careful evaluation judge. Follow the instructions exactly.", prompt, max_tokens=2000, temperature=0)
            hint = "\n\nReturn ONLY one JSON object that validates against this JSON schema (no prose, no markdown):\n" + json.dumps(schema.model_json_schema())
            txt = llm.chat("You are a careful evaluation judge. Follow the instructions exactly.", prompt + hint, json_mode=True, max_tokens=2500, temperature=0)
            data = llm.parse_json(txt)
            if data is None: raise ValueError("judge returned no JSON")
            return schema.model_validate(data)
        async def a_generate(self, prompt, schema=None, **kw): return self.generate(prompt, schema)
    return StudyPilotJudge()


def run(n=10, progress=lambda m, p: None, judge=None):
    if not llm.enabled() and judge is None: raise ValueError("DeepEval needs an AI judge: set OPENROUTER_API_KEY in .env, then retry.")
    from deepeval import metrics as M
    from deepeval.test_case import LLMTestCase
    idx = get_index(); judge = judge or make_judge()
    items = [i for i in evals.build_testset(n) if i["in_scope"] and i.get("reference") and i["truth_unit_ids"]]
    items = sorted(items, key=lambda i: i.get("group") != "team")[:n]   # hand-built team questions first
    if not items: raise ValueError("Upload course material first (Library tab).")
    rows, scores, errs = [], {k: [] for k in METRICS}, 0
    for i, it in enumerate(items):
        progress(f"DeepEval {i + 1}/{len(items)}", i / len(items))
        r = answer(None, it["question"], allow_outside=False)
        row = {"question": it["question"], "group": it.get("group"), "declined": not r["covered"]}
        if r["covered"]:
            ctx = [idx.by_id[h["unit_id"]]["text"] for h in r["retrieved"]]
            tc = LLMTestCase(input=it["question"], actual_output=re.sub(r"\[S\d+\]", "", r["answer"]).strip(), expected_output=it["reference"], retrieval_context=ctx)
            for k, cls in METRICS.items():
                try:
                    m = getattr(M, cls)(model=judge, threshold=0.5, include_reason=False, async_mode=False, verbose_mode=False); m.measure(tc)
                    if m.score is not None: row[k] = round(float(m.score), 3); scores[k].append(float(m.score))
                except Exception as e: errs += 1; row[k + "_error"] = str(e)[:120]
        rows.append(row)
    res = {"framework": "DeepEval " + __import__("importlib.metadata", fromlist=["version"]).version("deepeval"), "judge": judge.get_model_name(), "n_questions": len(items),
           "n_answered": sum(not r["declined"] for r in rows), "metric_errors": errs,
           "metrics": {k: (round(float(np.mean(v)), 3) if v else None) for k, v in scores.items()},
           "caveats": ["The judge is the same model family as the generator (self-evaluation bias). Independent human review is recommended for final evaluation.",
                       "Small samples (default 10 questions) give wide error bars; raise n for a firmer estimate (about 10 judge calls per question)."],
           "rows": rows, "generated": time.time()}
    (C.EVAL / "deepeval.json").write_text(json.dumps(res, indent=1)); progress("Done", 1.0); return res
