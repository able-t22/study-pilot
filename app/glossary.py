"""Grounded glossary: every key concept with the sentence in YOUR material that defines or uses it, plus its source. No AI needed, nothing invented."""
import re
from . import db, assess, nlp
from .retrieval import get_index, cite

DEF = re.compile(r"\b(is|are|means|refers to|defined as|denotes|called|measures|represents)\b", re.I)


def build():
    idx = get_index(); out, seen = [], set()
    topics = {t["id"]: t["name"] for t in db.q("SELECT id,name FROM topics")}
    by_topic = {}
    for u in idx.units:
        if u["kind"] != "figure": by_topic.setdefault(u["topic_id"], []).append(u)
    for c in db.q("SELECT name, topic_id FROM concepts ORDER BY name"):
        nm = c["name"].strip(); key = nm.lower()
        if key in seen or len(nm) < 3: continue
        nt = set(nlp.tokens(nm))
        if not nt: continue
        best = None
        for u in by_topic.get(c["topic_id"], []):
            for s in nlp.sentences(re.sub(r"^(Speaker notes: )", "", u["text"])):
                if not assess.good_sentence(s) or not nt <= set(nlp.tokens(s)): continue
                score = (2 if DEF.search(s) else 0) + (1 if s.lower().startswith(key) else 0) - len(s.split()) / 100
                if not best or score > best[0]: best = (score, s, u)
        if best:
            seen.add(key); out.append({"term": nm, "definition": best[1], "topic": topics.get(c["topic_id"], ""), "source": cite(best[2])})
    return out
