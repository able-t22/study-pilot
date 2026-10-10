"""Spaced-repetition review (SM-2 style) on top of grounded flashcards. Every grade also nudges the learner model, so reviewing makes
quizzes, recommendations and the schedule more personal. Cards keep their source (page / slide / timestamp)."""
import hashlib, json, time
from . import db, learner, revision, llm

DAY = 86400
GRADES = {"again": 0, "hard": 1, "good": 2, "easy": 3}


def _key(topic_id, front): return hashlib.sha1(f"{topic_id}|{front.strip().lower()}".encode()).hexdigest()[:16]


def add_cards(sid, topic_id, cards):
    """Insert grounded flashcards that are not already in the learner's deck. -> number added."""
    n, now = 0, time.time()
    for c in cards:
        k = _key(topic_id, c["front"])
        if db.q1("SELECT id FROM reviews WHERE student_id=? AND card_key=?", (sid, k)): continue
        db.ex("INSERT INTO reviews(student_id,topic_id,card_key,front,back,source,ease,interval,due,reps,lapses,last,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (sid, topic_id, k, c["front"], c["back"], json.dumps(c.get("source")), 2.5, 0.0, now, 0, 0, None, now)); n += 1
    return n


def build(sid, topic_ids=None, per_topic=8, lang="en"):
    with llm.request_budget(0):
        return _build(sid, topic_ids, per_topic, lang)

def _build(sid, topic_ids=None, per_topic=8, lang="en"):
    """Add flashcards for the given topics (default: the learner's weakest) to the deck."""
    mast = {m["topic_id"]: m for m in learner.get_mastery(sid)}
    ids = topic_ids or [m["topic_id"] for m in sorted(mast.values(), key=lambda m: m["p_eff"])[:4]]
    added = 0
    for t in ids:
        if t in mast: added += add_cards(sid, t, revision.flashcards(t, per_topic, lang=lang)[0])
    return {"added": added, "topics": [mast[t]["name"] for t in ids if t in mast], **stats(sid)}


def _fmt(r, now):
    return {"id": r["id"], "topic_id": r["topic_id"], "front": r["front"], "back": r["back"], "source": json.loads(r["source"]) if r["source"] else None,
            "reps": r["reps"], "lapses": r["lapses"], "new": r["reps"] == 0 and not r["last"], "preview": preview(r)}


def preview(r):
    """Next interval (days) for each grade, shown on the buttons."""
    return {g: round(_next(r["ease"], r["interval"], r["reps"], q)[1], 3) for g, q in GRADES.items()}


def _next(ease, interval, reps, q):
    """-> (ease, interval_days, reps). SM-2 variant with 4 grades; 'again' re-shows in 10 minutes."""
    if q == 0: return max(1.3, ease - 0.2), 10 / 1440, 0
    if reps == 0: iv = 1.0 if q == 2 else (0.5 if q == 1 else 3.0)
    elif reps == 1: iv = 3.0 if q == 2 else (1.5 if q == 1 else 6.0)
    else: iv = interval * (ease if q == 2 else 1.2 if q == 1 else ease * 1.3)
    return max(1.3, ease + (0.15 if q == 3 else -0.15 if q == 1 else 0)), max(iv, 0.5), reps + 1


def due(sid, limit=20, new_limit=8):
    """Due cards first (oldest due first), then up to new_limit never-seen cards."""
    now = time.time()
    rows = db.q("SELECT * FROM reviews WHERE student_id=? AND due<=? ORDER BY (reps=0), due LIMIT ?", (sid, now, 200))
    old = [r for r in rows if r["reps"] > 0 or r["last"]][:limit]; new = [r for r in rows if r["reps"] == 0 and not r["last"]][:new_limit]
    return [_fmt(r, now) for r in old + new][:limit]


def grade(sid, review_id, g):
    r = db.q1("SELECT * FROM reviews WHERE id=? AND student_id=?", (review_id, sid))
    if not r or g not in GRADES: raise ValueError("Unknown card or grade")
    q = GRADES[g]; ease, iv, reps = _next(r["ease"], r["interval"], r["reps"], q); now = time.time()
    lapses = r["lapses"] + (1 if q == 0 and r["reps"] > 0 else 0)
    db.ex("UPDATE reviews SET ease=?, interval=?, due=?, reps=?, lapses=?, last=? WHERE id=?", (ease, iv, now + iv * DAY, reps, lapses, now, review_id))
    learner.update(sid, r["topic_id"], q >= 2, "short", "medium", weight=0.4)   # recall evidence, weighted below a real quiz answer
    return {"next_due_days": round(iv, 3), **stats(sid)}


def stats(sid):
    now = time.time(); rows = db.q("SELECT reps, last, due, interval, lapses FROM reviews WHERE student_id=?", (sid,))
    seen = [r for r in rows if r["last"]]
    return {"total": len(rows), "due_now": sum(r["due"] <= now for r in rows), "new": sum(not r["last"] for r in rows),
            "mature": sum(r["interval"] >= 21 for r in rows), "reviewed_today": sum(bool(r["last"]) and now - (r["last"] or 0) < DAY for r in rows),
            "lapse_rate": round(sum(r["lapses"] for r in seen) / max(sum(r["reps"] + r["lapses"] for r in seen), 1), 3)}


def anki_tsv(sid):
    """Tab-separated file Anki can import (File -> Import). Columns: front, back (with source), tags."""
    names = {m["topic_id"]: m["name"] for m in learner.get_mastery(sid)}; out = []
    for r in db.q("SELECT * FROM reviews WHERE student_id=? ORDER BY topic_id, id", (sid,)):
        src = json.loads(r["source"]) if r["source"] else {}; esc = lambda x: str(x).replace("\t", " ").replace("\n", "<br>")
        out.append("\t".join([esc(r["front"]), esc(r["back"]) + f"<br><i>{esc(src.get('source_name', ''))} · {esc(src.get('label', ''))}</i>",
                              "StudyPilot " + names.get(r["topic_id"], "").replace(" ", "_")]))
    return "\n".join(out)
