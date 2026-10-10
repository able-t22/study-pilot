"""Learner model: Bayesian Knowledge Tracing per topic + forgetting-curve (spaced repetition) + adaptive policy + study planner."""
import math, random, re, time
from . import db

P_LEARN = 0.15
GUESS = {"mcq": 0.25, "short": 0.08, "numerical": 0.03}
SLIP = {"easy": 0.05, "medium": 0.10, "hard": 0.18}
LEVEL_PRIOR = {"beginner": 0.15, "intermediate": 0.35, "advanced": 0.60}
DAY = 86400.0
S0 = 1.5  # initial memory stability (days)


# ---------- pure model functions (shared with the simulator) ----------
def bkt_update(p, correct, guess, slip, learn=P_LEARN, weight=1.0):
    if correct: post = p * (1 - slip) / (p * (1 - slip) + (1 - p) * guess)
    else: post = p * slip / (p * slip + (1 - p) * (1 - guess))
    post = p + weight * (post - p)
    return min(0.99, max(0.01, post + (1 - post) * learn * weight))


def retrievability(stab, dt_days): return math.exp(-max(dt_days, 0) / max(stab, 0.1))
def effective(p, R): return p * (0.5 + 0.5 * R)
def stab_update(S, correct, weight=1.0): return S * (1 + 0.8 * weight) if correct else max(0.5, S * (1 - 0.5 * weight))
def target_difficulty(p): return "easy" if p < 0.4 else ("medium" if p < 0.7 else "hard")


def pick_topics(state, prereqs, n, rng, noise=0.05):
    """Greedy adaptive allocation: weak topics first, unlock prerequisites before dependants, diminishing returns."""
    need = {t: 1 - p for t, p in state.items()}
    dependants = {}
    for t, ps in prereqs.items():
        for pr in ps: dependants.setdefault(pr, []).append(t)
    for t in need:
        if any(state.get(pr, 1) < 0.45 for pr in prereqs.get(t, [])): need[t] *= 0.6
        if any(state.get(d, 1) < 0.5 for d in dependants.get(t, [])) and state[t] < 0.7: need[t] *= 1.15
    out = []
    for _ in range(n):
        t = max(need, key=lambda x: need[x] + rng.uniform(-noise, noise))
        out.append(t); need[t] *= 0.7
    return out


# ---------- persistence ----------
def top_topics():
    return db.q("SELECT * FROM topics WHERE parent_id IS NULL ORDER BY order_idx")


def prereq_map():
    m = {}
    for r in db.q("SELECT * FROM prereqs"): m.setdefault(r["topic_id"], []).append(r["prereq_id"])
    return m


def init_student(name, level="beginner", goal="", exam_date="", sid=None):
    sid = db.ex("INSERT INTO students(id,name,level,goal,exam_date,created) VALUES(?,?,?,?,?,?)", (sid, name, level, goal, exam_date, time.time()))
    ensure_rows(sid)
    return sid


def ensure_rows(sid, self_rating=None):
    st = db.q1("SELECT * FROM students WHERE id=?", (sid,))
    prior = LEVEL_PRIOR.get(st["level"], 0.2)
    have = {r["topic_id"] for r in db.q("SELECT topic_id FROM mastery WHERE student_id=?", (sid,))}
    for t in top_topics():
        if t["id"] not in have:
            db.ex("INSERT INTO mastery VALUES(?,?,?,?,?,?)", (sid, t["id"], (self_rating or {}).get(t["id"], prior), S0, 0, time.time()))


def get_mastery(sid, now=None):
    now = now or time.time(); ensure_rows(sid)
    rows = {r["topic_id"]: r for r in db.q("SELECT * FROM mastery WHERE student_id=?", (sid,))}
    out = []
    for t in top_topics():
        r = rows[t["id"]]; R = retrievability(r["stability"], (now - r["last_ts"]) / DAY)
        p = r["p_know"]; eff = effective(p, R) if r["n_obs"] else p
        out.append({"topic_id": t["id"], "name": t["name"], "p_know": round(p, 3), "p_eff": round(eff, 3), "retrievability": round(R, 3),
                    "n_obs": r["n_obs"], "stability_days": round(r["stability"], 2), "order": t["order_idx"],
                    "level": "strong" if eff >= 0.7 else "developing" if eff >= 0.4 else "weak"})
    return out


def update(sid, topic_id, correct, qtype, difficulty, weight=1.0):
    ensure_rows(sid)
    r = db.q1("SELECT * FROM mastery WHERE student_id=? AND topic_id=?", (sid, topic_id))
    now = time.time(); R = retrievability(r["stability"], (now - r["last_ts"]) / DAY)
    p0 = r["p_know"] * (0.7 + 0.3 * R) if r["n_obs"] else r["p_know"]  # forgetting decays belief before the update
    p = bkt_update(p0, correct, GUESS.get(qtype, 0.2), SLIP.get(difficulty, 0.1), weight=weight)
    S = stab_update(r["stability"], correct, weight)
    db.ex("UPDATE mastery SET p_know=?, stability=?, n_obs=n_obs+1, last_ts=? WHERE student_id=? AND topic_id=?", (p, S, now, sid, topic_id))
    db.ex("INSERT INTO mastery_log(student_id,topic_id,p_know,ts,src) VALUES(?,?,?,?,?)", (sid, topic_id, p, now, "chat" if weight < 1 else "quiz"))
    return p


NEG = re.compile(r"don'?t (understand|get)|confus|no idea|lost|stuck|why\b|not sure|explain again|hard to|क्यों|समझ नहीं", re.I)
POS = re.compile(r"got it|makes sense|i understand|clear now|easy|understood|समझ गया|समझ आ गया", re.I)


def conversation_signal(sid, topic_id, message):
    """Weak evidence from chat (weight 0.3): expressed confusion lowers, expressed understanding raises mastery."""
    if not topic_id: return None
    if NEG.search(message): update(sid, topic_id, False, "mcq", "medium", weight=0.3); return "confusion"
    if POS.search(message): update(sid, topic_id, True, "mcq", "medium", weight=0.3); return "understanding"
    return None


def recommend(sid, k=3):
    """Next best actions. Order: topics you have practised but not mastered (so progress is visible), then untouched topics whose prerequisites are fine,
    then topics that still need a weak prerequisite first."""
    m = {x["topic_id"]: x for x in get_mastery(sid)}; pm = prereq_map(); out = []
    for t, x in m.items():
        if x["p_eff"] >= 0.8: continue
        weak_pre = [m[p]["name"] for p in pm.get(t, []) if p in m and m[p]["p_eff"] < 0.45]
        reason = ("Memory is fading - review due" if x["retrievability"] < 0.6 and x["n_obs"] else
                  "Keep practising - improving but not there yet" if x["n_obs"] else "Not practised yet - start here")
        if weak_pre: reason = "Review prerequisite(s) first: " + ", ".join(weak_pre)
        out.append({"topic_id": t, "name": x["name"], "p_eff": x["p_eff"], "n_obs": x["n_obs"], "reason": reason, "_k": (bool(weak_pre), x["n_obs"] == 0, x["p_eff"] if x["n_obs"] else x["order"])})
    out.sort(key=lambda r: r["_k"])
    for r in out: r.pop("_k")
    return out[:k]


def schedule(sid, days, minutes_per_day, slot=30):
    m = {x["topic_id"]: x for x in get_mastery(sid)}; pm = prereq_map()
    state = {t: x["p_eff"] for t, x in m.items()}; S = {t: max(x["stability_days"], S0) for t, x in m.items()}
    last = {t: 0 for t in m}; plan = []
    from .retrieval import get_index
    first = {}
    for u in get_index().units:
        first.setdefault(u["topic_id"], f"{u['source_name']} {u['label']}")
    for d in range(days):
        slots = max(1, minutes_per_day // slot); items = []
        if d == days - 1 and days > 1:
            items.append({"topic": "All topics", "activity": "Full mock exam + review of mistakes", "minutes": slot}); slots -= 1
        for _ in range(max(slots, 0)):
            best, bn = None, -1
            for t in state:
                R = retrievability(S[t], d - last[t]); need = 1 - effective(state[t], R)
                if any(state.get(p, 1) < 0.5 for p in pm.get(t, [])): need *= 0.55
                if need > bn: best, bn = t, need
            t = best; act = "Learn from source" if state[t] < 0.4 else "Practice quiz" if state[t] < 0.75 else "Spaced review"
            items.append({"topic_id": t, "topic": m[t]["name"], "activity": act, "minutes": slot, "start_at": first.get(t, "")})
            state[t] = min(0.98, state[t] + 0.12 * (1 - state[t]) + 0.04); S[t] *= 1.6; last[t] = d
        plan.append({"day": d + 1, "items": items})
    return plan


def trajectory(sid):
    """Mean P(know) across topics after every learner-model update (quiz answers and chat signals) - shows personalisation over time."""
    st = db.q1("SELECT * FROM students WHERE id=?", (sid,)); tops = top_topics()
    if not st or not tops: return []
    cur = {t["id"]: LEVEL_PRIOR.get(st["level"], 0.2) for t in tops}
    pts = [{"i": 0, "mean": round(sum(cur.values()) / len(cur), 4), "src": "start", "ts": st["created"]}]
    for i, r in enumerate(db.q("SELECT * FROM mastery_log WHERE student_id=? ORDER BY id", (sid,)), 1):
        if r["topic_id"] in cur: cur[r["topic_id"]] = r["p_know"]
        pts.append({"i": i, "mean": round(sum(cur.values()) / len(cur), 4), "src": r["src"], "ts": r["ts"]})
    return pts[-300:]
