"""Teach-back (Feynman) check: the learner explains a topic in their own words; StudyPilot grades the explanation against the uploaded material.
 - coverage: which key concepts of the topic were actually explained, and where to find the missing ones
 - accuracy: sentences the material does not support are flagged as possible misconceptions (never silently accepted)
The result also feeds the learner model (lighter weight than a quiz answer)."""
import json, re, time
from . import db, llm, learner, revision, grounding, nlp, assess
from .retrieval import get_index, cite


def check(sid, topic_id, text, lang="en"):
    text = (text or "").strip()
    if len(text.split()) < 8: raise ValueError("Write at least a couple of sentences explaining the topic in your own words.")
    t = db.q1("SELECT * FROM topics WHERE id=?", (topic_id,))
    if not t: raise ValueError("Unknown topic")
    idx = get_index(); units = revision._units(topic_id, idx, 6) or [u for u in idx.units if u["topic_id"] == topic_id]
    if not units: raise ValueError("This topic has no material yet.")
    tt = set(nlp.tokens(text)); covered, missing = [], []
    for nm in dict.fromkeys(r["name"] for r in db.q("SELECT name FROM concepts WHERE topic_id=?", (topic_id,))):
        ct = set(nlp.tokens(nm))
        if ct: (covered if len(ct & tt) / len(ct) >= 0.6 else missing).append(nm)
    if not covered and not missing:   # no concept list: use the topic's most informative sentences as the checklist
        for s, u in revision._best_sentences(idx, units, 5):
            (covered if grounding.support(s, [{"text": text}]) >= 0.5 else missing).append(s[:80])
    hints = []
    for nm in missing[:5]:
        nt = set(nlp.tokens(nm)); best = next(iter(sorted(((s, u) for s, u in revision._best_sentences(idx, units, 60) if nt <= set(nlp.tokens(s))), key=lambda x: len(x[0]))), None)
        hints.append({"concept": nm, "hint": best[0] if best else None, "source": cite(best[1]) if best else None})
    sents = [s for s in nlp.sentences(text) if len(s.split()) >= 4]
    ok = grounding.verify(sents, units, lexical=(lang == "en")) if sents else []
    flagged = [s for s, k in zip(sents, ok) if not k]
    coverage = len(covered) / max(len(covered) + len(missing), 1); accuracy = (sum(ok) / len(ok)) if ok else 0.0
    score = round(0.6 * coverage + 0.4 * accuracy, 3); feedback = ""
    if llm.enabled():
        try:
            ctx = "\n".join(u["text"][:600] for u in units[:6])
            fb = llm.chat("You are a kind, precise tutor. Use ONLY the material. 3 short sentences: one thing they got right, the most important gap or mistake, one next step.",
                          f"MATERIAL:\n{ctx}\n\nSTUDENT EXPLANATION:\n{text[:1500]}\n\nMissing concepts: {', '.join(missing[:5]) or 'none'}\nPossibly unsupported: {' | '.join(flagged[:3]) or 'none'}", max_tokens=300)
            feedback = grounding.ground_text(fb, units, lexical=(lang == "en"))["text"]
        except Exception: pass
    if not feedback:
        feedback = (f"You covered {len(covered)} of {len(covered) + len(missing)} key ideas." + (f" Next, explain “{missing[0]}”." if missing else " Great coverage!") +
                    (" Some sentences are not supported by your material - check them against the sources." if flagged else ""))
    learner.update(sid, topic_id, score >= 0.6, "short", "medium", weight=0.6)
    res = {"topic": t["name"], "score": score, "coverage": round(coverage, 3), "accuracy": round(accuracy, 3), "covered": covered, "missing": hints, "flagged": flagged, "feedback": feedback}
    db.ex("INSERT INTO teachbacks(student_id,topic_id,body,score,result,created) VALUES(?,?,?,?,?,?)", (sid, topic_id, text, score, json.dumps(res), time.time()))
    return res


def history(sid, limit=10):
    return [{"id": r["id"], "topic_id": r["topic_id"], "score": r["score"], "created": r["created"]} for r in
            db.q("SELECT id, topic_id, score, created FROM teachbacks WHERE student_id=? ORDER BY id DESC LIMIT ?", (sid, limit))]
