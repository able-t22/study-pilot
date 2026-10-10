"""Answer-quality check: faithfulness, answer relevancy, context precision/recall and refusal accuracy.
Implemented natively (no extra paid dependency). LLM-judged when a provider is set; lexical otherwise."""
import json, random, re, time
import numpy as np
from . import llm, nlp, assess, grounding, config as C
from .retrieval import get_index
from .tutor import answer

OFF_TOPIC = ["What is the capital of Australia?", "How do I bake sourdough bread?", "Who won the 2018 FIFA World Cup?",
             "What is the boiling point of mercury?", "Explain the plot of Hamlet.", "How do vaccines trigger immunity?",
             "What is the best way to learn guitar chords?", "Who painted the Mona Lisa?", "How many moons does Jupiter have?",
             "What are the rules of cricket's LBW?", "Describe the causes of the French Revolution.", "How does a jet engine work?"]


def _resolve(idx, t):
    """Team test-set truth {source, page|slide|at} -> unit ids in THIS learner's knowledge base."""
    out = []
    for u in idx.units:
        if u.get("source_name") != t["source"]: continue
        L_ = u["loc"]
        if "page" in t and L_.get("page") == t["page"] or "slide" in t and L_.get("slide") == t["slide"] or \
           "at" in t and "t0" in L_ and L_["t0"] <= t["at"] <= L_["t1"]: out.append(u["id"])
    return out


def team_testset(idx):
    """Hand-written questions with known source locations (tests/testset_intro_ml.json) for whichever course sources are present."""
    try: d = json.loads((C.ROOT / "tests" / "testset_intro_ml.json").read_text())
    except Exception: return []
    names = {u.get("source_name") for u in idx.units}
    if not set(d.get("required_sources", [])) <= names: return []   # a different course is loaded: skip rather than mis-score
    items = []
    for it in d["in_scope"]:
        ids = sorted({i for t in it["truth"] for i in _resolve(idx, t)})
        if ids: items.append({"question": it["question"], "reference": it["reference"], "truth_unit_ids": ids, "in_scope": True, "group": "team"})
    items += [{"question": q, "reference": "", "truth_unit_ids": [], "in_scope": False, "group": "adjacent"} for q in d.get("adjacent_off_material", [])]
    return items


def build_testset(n=20, seed=7):
    idx = get_index(); rng = random.Random(seed)
    units = [u for u in idx.units if u["kind"] in ("text", "transcript") and len(u["text"].split()) >= 25]
    rng.shuffle(units); items = team_testset(idx)
    for u in units[:n]:
        if llm.enabled():
            r = llm.chat_json("You write exam questions.", f"PASSAGE:\n{u['text'][:1000]}\n\nWrite ONE natural student question answerable only from this "
                              'passage, phrased in your own words (do not copy phrases). JSON: {"question":"...","reference":"short reference answer"}', max_tokens=300)
            if isinstance(r, dict) and r.get("question"):
                items.append({"question": r["question"], "reference": r.get("reference", ""), "truth_unit_ids": [u["id"]], "in_scope": True, "group": "auto"}); continue
        # offline: keyword-style query from salient terms (LEXICAL -> optimistic, flagged in caveats)
        qs = assess.cloze_questions(idx, [u], 1, rng, ("short",))
        if qs:
            s = qs[0]["explanation"].split("“", 1)[-1].rstrip("”")
            words = [w for w in nlp.tokens(s)][:7]
            items.append({"question": "What does the material say about " + " ".join(words[:5]) + "?", "reference": s, "truth_unit_ids": [u["id"]], "in_scope": True, "group": "auto"})
    for q in OFF_TOPIC: items.append({"question": q, "reference": "", "truth_unit_ids": [], "in_scope": False, "group": "off"})
    try:
        extra = json.loads((C.EVAL / "custom_testset.json").read_text())
        items += extra
    except Exception: pass
    return items


def _match(h, truth, idx):
    for tid in truth:
        t = idx.by_id[tid]
        if h["id"] == tid: return True
        if h["source_id"] != t["source_id"]: continue
        for key in ("page", "slide"):
            if key in h["loc"] and h["loc"].get(key) == t["loc"].get(key): return True
        if "t0" in h["loc"] and "t0" in t["loc"] and abs(h["loc"]["t0"] - t["loc"]["t0"]) < 60: return True
    return False


def _faith(ans, ctx):
    claims = [re.sub(r"\[S\d+\]", "", s).strip() for s in nlp.sentences(re.sub(r"^[-•*]\s*", "", ans, flags=re.M))]
    claims = [c for c in claims if len(c.split()) >= 4 and not c.lower().startswith("from your course")]
    if not claims: return None
    if llm.enabled():
        r = llm.chat_json("You are a strict fact-checker.", "CONTEXT:\n" + ctx[:6000] + "\n\nCLAIMS:\n" + "\n".join(f"{i + 1}. {c}" for i, c in enumerate(claims)) +
                          '\n\nFor each claim say whether it is fully supported by the context. JSON: {"supported":[true,false,...]}', max_tokens=300)
        if isinstance(r, dict) and isinstance(r.get("supported"), list) and r["supported"]:
            return sum(bool(x) for x in r["supported"]) / len(r["supported"])
    ct = set(nlp.tokens(ctx)); sc = []
    for c in claims:
        t = nlp.tokens(c); sc.append(sum(x in ct for x in t) / max(len(t), 1) >= 0.7)
    return sum(sc) / len(sc)


def _relevancy(q, a):
    if llm.enabled():
        r = llm.chat_json("You rate answers.", f"Question: {q}\nAnswer: {a}\nRate 0-1 how directly and completely the answer addresses the question. JSON {{\"score\":0.0}}", max_tokens=60)
        if isinstance(r, dict) and "score" in r: return float(r["score"])
    idx = get_index(); v = idx.tfidf.transform([q, re.sub(r"\[S\d+\]", "", a)])
    return float((v[0] @ v[1].T).toarray()[0, 0])


def run(n=20, progress=lambda m, p: None):
    idx = get_index(); items = build_testset(n); rows = []
    for i, it in enumerate(items):
        progress(f"Evaluating {i + 1}/{len(items)}", i / len(items))
        t0 = time.time(); r = answer(None, it["question"], allow_outside=False)
        dt = time.time() - t0; row = {"question": it["question"], "group": it.get("group", "auto"), "in_scope": it["in_scope"], "declined": not r["covered"], "latency_s": round(dt, 2)}
        if it["in_scope"] and it["truth_unit_ids"]:
            ret = [h for h in r["retrieved"]]; units = [idx.by_id[h["unit_id"]] for h in ret]
            rel = [1 if _match(u, it["truth_unit_ids"], idx) else 0 for u in units]
            row["context_recall"] = float(any(rel))
            prec = [sum(rel[:k + 1]) / (k + 1) for k in range(len(rel)) if rel[k]]
            row["context_precision"] = float(np.mean(prec)) if prec else 0.0
            row["first_hit_rank"] = (rel.index(1) + 1) if any(rel) else None
            row["hit_at_1"] = float(bool(rel and rel[0])); row["mrr"] = 1 / row["first_hit_rank"] if row["first_hit_rank"] else 0.0
            if it.get("reference"):  # RAGAS-style recall: how much of the reference answer is attributable to the retrieved context
                refs = [x for x in nlp.sentences(it["reference"]) if len(x.split()) >= 1] or [it["reference"]]
                row["context_recall_ref"] = float(np.mean([grounding.support(x, units) >= 0.5 for x in refs]))
            cit = [c["unit_id"] for c in r.get("citations", []) if "unit_id" in c]
            if cit: row["citation_accuracy"] = float(np.mean([_match(idx.by_id[c], it["truth_unit_ids"], idx) for c in cit]))
            if r["covered"]:
                ctx = "\n".join(u["text"] for u in units)
                row["faithfulness"] = _faith(r["answer"], ctx); row["answer_relevancy"] = _relevancy(it["question"], r["answer"])
        rows.append(row)
    def agg(sub):
        ins = [r for r in sub if r["in_scope"]]; outs = [r for r in sub if not r["in_scope"]]
        mean = lambda k: round(float(np.mean([r[k] for r in ins if r.get(k) is not None])), 3) if any(r.get(k) is not None for r in ins) else None
        return {"n_in_scope": len(ins), "n_off_material": len(outs), "faithfulness": mean("faithfulness"), "answer_relevancy": mean("answer_relevancy"),
                "context_precision": mean("context_precision"), "context_recall": mean("context_recall"), "context_recall_ref": mean("context_recall_ref"),
                "hit_at_1": mean("hit_at_1"), "mrr": mean("mrr"), "citation_accuracy": mean("citation_accuracy"),
                "answer_rate_in_scope": round(float(np.mean([not r["declined"] for r in ins])), 3) if ins else None,
                "correct_refusal_rate_off_material": round(float(np.mean([r["declined"] for r in outs])), 3) if outs else None,
                "mean_latency_s": round(float(np.mean([r["latency_s"] for r in sub])), 2) if sub else None}
    ins = [r for r in rows if r["in_scope"]]; outs = [r for r in rows if not r["in_scope"]]
    groups = {g: agg([r for r in rows if r["group"] == g or (g == "team" and r["group"] == "adjacent")]) for g in ("team",) if any(r["group"] == "team" for r in rows)}
    adj = [r for r in rows if r["group"] == "adjacent"]
    res = {"provider": C.PROVIDER, "framework": "StudyPilot-native (RAGAS metric definitions)", "n_in_scope": len(ins), "n_off_material": len(outs),
           "metrics": agg(rows), "team_set": groups.get("team"), "adjacent_refusal_rate": round(float(np.mean([r["declined"] for r in adj])), 3) if adj else None,
           "caveats": ([] if llm.enabled() else
                       ["Offline mode: auto-generated questions are keyword-style and faithfulness/relevancy are lexical proxies -> metrics are OPTIMISTIC. "
                        "Configure an LLM provider for LLM-judged faithfulness and independently-phrased test questions. The hand-written team set is unaffected by this."]) +
                      ["Off-material queries are generic; a course that genuinely covers one of them will score a (correct) non-refusal as a miss.",
                       "Context recall/precision use ground-truth source locations (same unit, same page/slide, or video within 60 s); context_recall_ref is the RAGAS-style reference-attribution variant."],
           "rows": rows, "generated": time.time()}
    (C.EVAL / "rag_eval.json").write_text(json.dumps(res, indent=1))
    progress("Done", 1.0)
    return res
