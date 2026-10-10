"""Evidence-based study actions and a mistake notebook; no generation calls required."""
import time
from . import db, learner, srs
from .retrieval import get_index, cite


def mistakes(student_id):
    # Only the latest response to each question counts: successful retries clear it.
    rows = db.q("SELECT a.question_id, a.response, a.ts, q.stem, q.answer, q.explanation, q.topic_id, q.unit_id "
                "FROM attempts a JOIN questions q ON q.id=a.question_id "
                "WHERE a.student_id=? AND a.correct=0 AND NOT EXISTS "
                "(SELECT 1 FROM attempts b WHERE b.student_id=a.student_id AND b.question_id=a.question_id AND b.id>a.id) "
                "ORDER BY a.id DESC", (student_id,))
    idx = get_index()
    names = {t["id"]: t["name"] for t in learner.top_topics()}
    return [{**r, "topic": names.get(r["topic_id"], ""), "source": cite(idx.by_id[r["unit_id"]])}
            for r in rows if r["unit_id"] in idx.by_id]


def overview(student_id):
    st = db.q1("SELECT * FROM students WHERE id=?", (student_id,))
    if not st: raise ValueError("Learner not found")
    mastery = learner.get_mastery(student_id)
    observed = [m for m in mastery if m["n_obs"] > 0]
    errors = mistakes(student_id)
    reviews = srs.stats(student_id)
    ready = sum(m["p_eff"] >= .7 for m in observed)
    return {"student": st, "topics": len(mastery), "practised": len(observed), "strong": ready,
            "mastery": round(sum(m["p_eff"] for m in observed) / len(observed), 3) if observed else None,
            "reviews": reviews, "mistakes": errors, "recommendations": learner.recommend(student_id),
            "generated_at": time.time()}
