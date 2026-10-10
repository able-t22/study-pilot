"""Audio Overview: a two-host study conversation about YOUR weakest topics (NotebookLM-style, but personalised by the learner model).
Every factual turn carries the source unit it came from and is fact-checked against it; unsupported turns are dropped."""
import re
from . import db, llm, learner, revision, grounding, lang as L
from .retrieval import get_index, cite

HOSTS = ("Alex", "Sam")


def _pick(sid, topic_ids):
    mast = sorted(learner.get_mastery(sid), key=lambda m: m["p_eff"]); idx = get_index()
    ok = lambda m: len(revision._units(m["topic_id"], idx, 8)) > 0
    chosen = [m for m in mast if m["topic_id"] in topic_ids and ok(m)] if topic_ids else [m for m in mast if ok(m)][:3]
    return chosen, idx


def build(sid, topic_ids=None, lang="en"):
    lang = L.valid(lang); chosen, idx = _pick(sid, topic_ids or [])
    if not chosen: raise ValueError("Not enough material yet: upload and analyse some sources first.")
    turns, claims, dropped = [], 0, 0
    for m in chosen:
        units = revision._units(m["topic_id"], idx, 8)[:6]; got = []
        if llm.enabled():
            ctx = "\n\n".join(f"[U{u['id']}] {u['text'][:700]}" for u in units)
            r = llm.chat_json("You write lively, accurate two-host study podcasts (hosts Alex and Sam) using ONLY the excerpts. Never add facts that are not in them.",
                              f"TOPIC: {m['name']} (the listener's mastery is {round(m['p_eff'] * 100)}%, so explain from the basics and use one concrete analogy)\n{ctx}\n\n"
                              "Write 8-10 short turns (each <= 45 words) alternating Alex and Sam: Sam asks natural questions, Alex explains, and one turn near the end gives a quick self-check question. "
                              'Return a JSON object with a turns list: {"turns":[{"speaker":"Alex|Sam","text":"...","source_unit_id":N or null for pure chatter}]}' +
                              (f". Speak in {L.prompt_name(lang)}." if lang != "en" else ""), max_tokens=2200)
            for t in (r if isinstance(r, list) else r.get("turns", []) if isinstance(r, dict) else []):
                try:
                    sp = t["speaker"] if t["speaker"] in HOSTS else HOSTS[len(got) % 2]; u = idx.by_id.get(int(re.sub(r"\D", "", str(t.get("source_unit_id") or "")) or -1))
                    got.append({"speaker": sp, "text": str(t["text"]).strip(), "unit": u, "topic": m["name"]})
                except Exception: pass
            fact = [i for i, t in enumerate(got) if t["unit"]]
            if fact:
                ok = grounding.verify([got[i]["text"] for i in fact], units, lexical=(lang == "en")); claims += len(fact)
                bad = {i for i, k in zip(fact, ok) if not k}; dropped += len(bad); got = [t for i, t in enumerate(got) if i not in bad]
        if not got:  # offline / unusable AI reply: scripted conversation built from the best sentences of the material
            picks = revision._best_sentences(idx, units, 3); nm = m["name"]
            got = [{"speaker": "Alex", "text": f"Let's work on {nm}. It's one of the places where a little revision pays off most.", "unit": None, "topic": nm}]
            asks = [f"So what's the core idea of {nm}?", "What else should I keep in mind?", "Anything that usually trips people up?"]
            for (s, u), ask in zip(picks, asks):
                got += [{"speaker": "Sam", "text": ask, "unit": None, "topic": nm}, {"speaker": "Alex", "text": s, "unit": u, "topic": nm}]; claims += 1
            got.append({"speaker": "Sam", "text": "Got it. I'll test myself with the flashcards next.", "unit": None, "topic": nm})
        turns += got
    if turns and turns[0]["speaker"] != "Alex": turns.insert(0, {"speaker": "Alex", "text": "Welcome to your personal study overview.", "unit": None, "topic": ""})
    # a Sam question left dangling by a dropped answer reads badly: remove it
    clean = [t for i, t in enumerate(turns) if not (t["speaker"] == "Sam" and t["text"].strip().endswith("?") and i + 1 < len(turns) and turns[i + 1]["speaker"] == "Sam")]
    out = [{"speaker": t["speaker"], "text": t["text"], "topic": t["topic"], "source": cite(t["unit"]) if t["unit"] else None} for t in clean]
    return {"title": "Audio overview: " + ", ".join(m["name"] for m in chosen), "lang": lang, "turns": out, "topics": [m["name"] for m in chosen],
            "grounding": {"factual_turns": claims, "dropped": dropped, "supported_pct": round(1 - dropped / max(claims, 1), 3)}}
