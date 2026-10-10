"""Audits that make the learner model trustworthy:
 - kb_integrity: topics / concepts / prerequisites well-formed, every unit traceable to page / slide / video timestamp.
 - question_audit: answer keys supported by their source, MCQ well-formed, topic tags agree with retrieval, difficulty tags track real correctness,
   and the learner model (BKT replay over real attempts) predicts answers better than a base-rate guess (Brier skill score)."""
import json, time
import numpy as np
from . import db, learner, grounding, assess, config as C
from .retrieval import get_index

ORIGIN_KEYS = ("page", "slide", "t0")


def kb_integrity():
    idx = get_index(); U = [u for u in idx.units]; n = len(U)
    topics = db.q("SELECT id,name,parent_id FROM topics"); tids = {t["id"] for t in topics}; top = [t for t in topics if not t["parent_id"]]
    edges = [(r["topic_id"], r["prereq_id"]) for r in db.q("SELECT topic_id, prereq_id FROM prereqs")]
    graph = {}
    for a, b in edges: graph.setdefault(a, []).append(b)
    state = {}

    def cyc(v):
        state[v] = 1
        for w in graph.get(v, []):
            if state.get(w) == 1 or (w not in state and cyc(w)): return True
        state[v] = 2; return False
    has_cycle = any(cyc(v) for v in list(graph) if v not in state)
    sources = {r["id"] for r in db.q("SELECT id FROM sources")}
    n_concepts = db.q1("SELECT COUNT(*) n FROM concepts")["n"]
    withconcept = {r["topic_id"] for r in db.q("SELECT DISTINCT topic_id FROM concepts")}
    linked = {a for a, _ in edges} | {b for _, b in edges}
    pct = lambda k: round(k / max(n, 1), 3)
    res = {"units": n, "units_with_origin": pct(sum(any(k in u["loc"] for k in ORIGIN_KEYS) for u in U)), "units_with_label": pct(sum(bool(u["label"]) for u in U)),
           "units_with_topic": pct(sum(u["topic_id"] in tids for u in U)), "units_with_existing_source": pct(sum(u["source_id"] in sources for u in U)),
           "topics": len(top), "subtopics": len(topics) - len(top), "concepts": n_concepts, "topics_with_concepts": round(len(withconcept & {t["id"] for t in top}) / max(len(top), 1), 3),
           "prereq_edges": len(edges), "prereq_edges_valid": all(a in tids and b in tids and a != b for a, b in edges), "prereq_graph_acyclic": not has_cycle,
           "topics_linked_by_prereq": round(len(linked & {t["id"] for t in top}) / max(len(top), 1), 3),
           "by_source_kind": {}}
    for u in U:
        k = u.get("source_kind") or "?"; d = res["by_source_kind"].setdefault(k, {"units": 0, "with_origin": 0}); d["units"] += 1; d["with_origin"] += any(x in u["loc"] for x in ORIGIN_KEYS)
    res["pass"] = bool(n and res["units_with_origin"] == 1.0 and res["units_with_topic"] == 1.0 and res["prereq_edges_valid"] and res["prereq_graph_acyclic"])
    return res


def _replay(rows):
    """BKT replay in answer order. Returns (predicted P(correct), outcomes) using only evidence available BEFORE each answer."""
    st, preds, ys = {}, [], []
    for r in rows:
        key = (r["student_id"], r["topic_id"]); p = st.get(key, learner.LEVEL_PRIOR.get(r["level"], 0.2))
        g, sl = learner.GUESS[r["qtype"]], learner.SLIP[r["difficulty"]]
        preds.append(g + (1 - g - sl) * p); ys.append(int(r["correct"])); st[key] = learner.bkt_update(p, bool(r["correct"]), g, sl)
    return np.array(preds), np.array(ys)


def question_audit():
    idx = get_index(); Q = db.q("SELECT * FROM questions"); res = {"questions": len(Q)}
    if not Q: return {**res, "note": "No questions yet - run a quiz first."}
    V = [q for q in Q if q["verified"]]; res["verified_rate"] = round(len(V) / len(Q), 3)
    res["cloze_share"] = round(sum(assess._is_cloze(q["stem"]) for q in Q) / len(Q), 3)
    key_ok, mcq_ok, mcq_n, tag_top1, tag_top3, src_top5, n_ret = [], [], 0, 0, 0, 0, 0
    for q in V:
        q = assess._hydrate(q); u = idx.by_id.get(q["unit_id"])
        if not u: continue
        txt = u["text"]
        key_ok.append(assess.norm(q["answer"]) in assess.norm(txt) or grounding.support(q["answer"], [u]) >= 0.6 or bool(q["extra"].get("calc")))
        if q["qtype"] == "mcq":
            mcq_n += 1; o = q["options"] or []
            mcq_ok.append(len(o) >= 3 and len({assess.norm(x) for x in o}) == len(o) and sum(assess.norm(x) == assess.norm(q["answer"]) for x in o) == 1)
        hits = idx.search(q["stem"] + " " + str(q["answer"]), k=5)
        if hits:
            n_ret += 1; tops = [h["topic_id"] for h in hits]; tag_top1 += tops[0] == q["topic_id"]; tag_top3 += q["topic_id"] in tops[:3]; src_top5 += any(h["id"] == q["unit_id"] for h in hits)
    res.update(answer_key_supported=round(float(np.mean(key_ok)), 3) if key_ok else None, mcq_well_formed=round(float(np.mean(mcq_ok)), 3) if mcq_ok else None, mcq_checked=mcq_n,
               topic_tag_agreement_top1=round(tag_top1 / n_ret, 3) if n_ret else None, topic_tag_agreement_top3=round(tag_top3 / n_ret, 3) if n_ret else None,
               source_unit_in_top5=round(src_top5 / n_ret, 3) if n_ret else None)
    rows = db.q("SELECT a.student_id, a.correct, a.ts, q.topic_id, q.qtype, q.difficulty, s.level FROM attempts a JOIN questions q ON q.id=a.question_id "
                "JOIN students s ON s.id=a.student_id ORDER BY a.ts, a.id")
    res["attempts"] = len(rows)
    if rows:
        byd = {}
        for r in rows: byd.setdefault(r["difficulty"], []).append(r["correct"])
        res["correct_rate_by_difficulty"] = {d: {"n": len(v), "rate": round(float(np.mean(v)), 3)} for d, v in byd.items()}
        rates = [np.mean(byd[d]) for d in ("easy", "medium", "hard") if len(byd.get(d, [])) >= 5]
        res["difficulty_tags_monotonic"] = bool(all(a >= b - 0.02 for a, b in zip(rates, rates[1:]))) if len(rates) >= 2 else None
        if len(rows) >= 20:
            p, y = _replay(rows); brier = float(np.mean((p - y) ** 2)); base = float(np.mean((y.mean() - y) ** 2))
            half = len(y) // 2; late = float(np.mean((p[half:] - y[half:]) ** 2)); early = float(np.mean((p[:half] - y[:half]) ** 2))
            bins = np.clip((p * 5).astype(int), 0, 4)
            res["learner_model"] = {"brier": round(brier, 4), "brier_base_rate": round(base, 4), "skill_score": round(1 - brier / base, 4) if base else None,
                                    "brier_first_half": round(early, 4), "brier_second_half": round(late, 4),
                                    "calibration": [{"bin": f"{b / 5:.1f}-{(b + 1) / 5:.1f}", "n": int((bins == b).sum()), "predicted": round(float(p[bins == b].mean()), 3), "observed": round(float(y[bins == b].mean()), 3)}
                                                    for b in range(5) if (bins == b).any()]}
    res["caveats"] = ["answer_key_supported / topic_tag_agreement are retrieval-and-lexical proxies, not human grading; use them to catch regressions and bad tags, "
                      "and spot-check a sample by hand.", "learner_model needs real attempts (>= 20); skill_score > 0 means BKT predicts answers better than a constant base-rate guess."]
    return res


def run():
    out = {"kb": kb_integrity(), "questions": question_audit(), "generated": time.time()}
    (C.EVAL / "audit.json").write_text(json.dumps(out, indent=1)); return out
