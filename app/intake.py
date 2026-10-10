"""New-learner onboarding: a short intake conversation (goal, level, time, self-rating per topic, free text) that seeds the learner model,
followed by a diagnostic quiz (assess.start kind='diagnostic') that replaces the self-reported prior with evidence.
Self-reports are noisy, so they only set a *prior* (blended with the level prior); the first answered questions quickly dominate it (BKT)."""
import json, re, time
from . import db, llm, learner, nlp

RATING_PRIOR = {"new": 0.10, "some": 0.30, "good": 0.55}
WEAK_WORDS = re.compile(r"\b(weak|struggl\w*|hard|difficult|confus\w*|don'?t (?:understand|know)|never (?:learn|studied)\w*|new to|lost)\b", re.I)
STRONG_WORDS = re.compile(r"\b(strong|good at|comfortable|confident|know well|already know|familiar|easy|revising|learnt|learned)\b", re.I)


def get(sid):
    r = db.q1("SELECT data, created FROM intake WHERE student_id=?", (sid,))
    return {"done": bool(r), "data": json.loads(r["data"]) if r else None, "created": r["created"] if r else None}


def interpret(text, topics):
    """Free text ('I struggle with SQL joins but I'm fine with basics') -> {'weak': [topic_id], 'strong': [topic_id]}."""
    text = (text or "").strip()
    if not text or not topics: return {"weak": [], "strong": []}
    if llm.enabled():
        r = llm.chat_json("You read a student's self-description and map it to the course topics. Only use topics from the list.",
                          "TOPICS:\n" + "\n".join(f"{t['id']}: {t['name']}" for t in topics) + f"\n\nSTUDENT SAYS: {text[:800]}\n\n"
                          'Return JSON {"weak":[topic ids they struggle with or are new to],"strong":[topic ids they already know well]}.', max_tokens=300)
        if isinstance(r, dict):
            ids = {t["id"] for t in topics}; g = lambda k: [int(x) for x in r.get(k, []) if str(x).lstrip("-").isdigit() and int(x) in ids]
            return {"weak": g("weak"), "strong": g("strong")}
    weak, strong = [], []   # offline: sentence-level keyword matching of topic words
    for s in re.split(r"[.;!\n]|\bbut\b", text, flags=re.I):
        st = set(nlp.tokens(s))
        hit = [t["id"] for t in topics if st & set(nlp.tokens(t["name"]))]
        if WEAK_WORDS.search(s): weak += hit
        elif STRONG_WORDS.search(s): strong += hit
    return {"weak": sorted(set(weak)), "strong": sorted(set(strong) - set(weak))}


def apply(sid, data):
    """Persist the intake, update the profile, and seed per-topic priors. Never overrides topics that already have answered questions."""
    topics = learner.top_topics()
    level = data.get("level") if data.get("level") in learner.LEVEL_PRIOR else "beginner"
    db.ex("UPDATE students SET level=?, goal=?, exam_date=? WHERE id=?", (level, str(data.get("goal", ""))[:200], str(data.get("exam_date", ""))[:10], sid))
    learner.ensure_rows(sid)
    base = learner.LEVEL_PRIOR[level]; rating = {int(k): v for k, v in (data.get("self_rating") or {}).items() if str(k).isdigit()}
    free = interpret(data.get("notes", ""), topics); seeded = {}
    for t in topics:
        p = base
        if rating.get(t["id"]) in RATING_PRIOR: p = 0.4 * base + 0.6 * RATING_PRIOR[rating[t["id"]]]
        if t["id"] in free["weak"]: p = min(p, 0.12)
        elif t["id"] in free["strong"]: p = max(p, 0.5)
        seeded[t["id"]] = round(min(max(p, 0.05), 0.85), 3)
        db.ex("UPDATE mastery SET p_know=? WHERE student_id=? AND topic_id=? AND n_obs=0", (seeded[t["id"]], sid, t["id"]))
    data = {**data, "level": level, "free_text_weak": free["weak"], "free_text_strong": free["strong"]}
    db.ex("DELETE FROM intake WHERE student_id=?", (sid,)); db.ex("INSERT INTO intake(student_id,data,created) VALUES(?,?,?)", (sid, json.dumps(data), time.time()))
    return {"seeded": seeded, "interpreted": free}
