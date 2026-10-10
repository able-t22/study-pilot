"""Knowledge-base structuring: topics -> subtopics -> concepts -> prerequisites, every unit tagged."""
import json, re
import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize
from . import db, llm, nlp
from .retrieval import get_index


def _cluster(X, k, seed=0):
    n = X.shape[0]
    if k <= 1 or n < 2: return np.zeros(n, dtype=int)
    Z = X
    try:
        nc = min(40, X.shape[1] - 1, n - 1)
        if nc >= 2: Z = normalize(TruncatedSVD(nc, random_state=seed).fit_transform(X))
        else: Z = X.toarray()
    except Exception:
        Z = X.toarray()
    return KMeans(n_clusters=k, n_init=10, random_state=seed).fit_predict(Z)


def _top_terms(idx, rows, n=6):
    m = np.asarray(idx.X[rows].mean(axis=0)).ravel(); names = idx.tfidf.get_feature_names_out()
    out = []
    for j in np.argsort(-m):
        t = idx.surface(names[j])
        if any(t in o or o in t for o in out): continue
        out.append(t)
        if len(out) >= n: break
    return out


def _samples(idx, rows, n=5, chars=260):
    return [f"- {idx.units[i]['text'][:chars]}" for i in rows[:n]]


def build(progress=lambda m, p: None, use_ai=True):
    idx = get_index(force=True); n = idx.n
    if n == 0: raise ValueError("No content ingested yet.")
    db.reset_analysis()
    k = int(min(12, max(3, round(n / 3)))) if n >= 9 else (2 if n >= 4 else 1)
    lab = _cluster(idx.X, k)
    # reading-order key per cluster
    per_src = {}
    for u in idx.units: per_src[u["source_id"]] = per_src.get(u["source_id"], 0) + 1
    pos = np.array([u["source_id"] + u["seq"] / per_src[u["source_id"]] for u in idx.units])
    clusters = sorted(set(lab), key=lambda c: pos[lab == c].mean())
    topic_ids, topic_rows = [], {}
    for oi, c in enumerate(clusters):
        progress(f"Naming topic {oi + 1}/{len(clusters)}", 0.1 + 0.7 * oi / len(clusters))
        rows = [i for i in range(n) if lab[i] == c]
        rows.sort(key=lambda i: (idx.units[i]["source_id"], idx.units[i]["seq"]))
        sub = _cluster(idx.X[rows], 2 if len(rows) >= 6 else 1, seed=1) if len(rows) >= 4 else np.zeros(len(rows), int)
        subs = {s: [rows[j] for j in range(len(rows)) if sub[j] == s] for s in sorted(set(sub))}
        terms = _top_terms(idx, rows, 8)
        info = None
        if use_ai and llm.enabled():
            prompt = "Course material excerpts for ONE topic cluster:\n" + "\n".join(_samples(idx, rows, 8)) + "\n\nSub-clusters:\n" + \
                "\n".join(f"[{chr(65 + s)}]\n" + "\n".join(_samples(idx, r, 3)) for s, r in subs.items()) + \
                '\n\nReturn JSON: {"name": short topic title (2-5 words), "summary": 1-2 sentence summary, "concepts": [6-10 key concept names ' \
                'actually present in the text], "subtopics": [{"cluster": "A", "name": "...", "concepts": ["..."]} ...one per sub-cluster]}'
            info = llm.chat_json("You are a curriculum designer structuring course material into topics.", prompt, max_tokens=1200)
        if not isinstance(info, dict) or not info.get("name"):
            info = {"name": " · ".join(t.title() for t in terms[:3]), "summary": "Covers: " + ", ".join(terms[:6]) + ".",
                    "concepts": terms[:8], "subtopics": [{"cluster": chr(65 + s), "name": ", ".join(t.title() for t in _top_terms(idx, r, 2)),
                                                          "concepts": _top_terms(idx, r, 4)} for s, r in subs.items()]}
        tid = db.ex("INSERT INTO topics(name,parent_id,summary,order_idx) VALUES(?,?,?,?)", (info["name"][:80], None, info.get("summary", ""), oi))
        topic_ids.append(tid); topic_rows[tid] = rows
        sub_info = {s.get("cluster"): s for s in info.get("subtopics", []) if isinstance(s, dict)}
        sub_ids = {}
        for s, r in subs.items():
            si = sub_info.get(chr(65 + s), {})
            nm = si.get("name") or ", ".join(t.title() for t in _top_terms(idx, r, 2))
            sub_ids[s] = db.ex("INSERT INTO topics(name,parent_id,summary,order_idx) VALUES(?,?,?,?)", (str(nm)[:80], tid, "", s))
            for cn in (si.get("concepts") or [])[:6]:
                db.ex("INSERT INTO concepts(topic_id,subtopic_id,name) VALUES(?,?,?)", (tid, sub_ids[s], str(cn)[:80]))
        have = {c["name"].lower() for c in db.q("SELECT name FROM concepts WHERE topic_id=?", (tid,))}
        for cn in info.get("concepts", [])[:10]:
            if str(cn).lower() not in have:
                db.ex("INSERT INTO concepts(topic_id,subtopic_id,name) VALUES(?,?,?)", (tid, None, str(cn)[:80]))
        concepts = db.q("SELECT * FROM concepts WHERE topic_id=?", (tid,))
        ctoks = [(c["id"], set(nlp.tokens(c["name"]))) for c in concepts]
        unit_tags = []
        for j, i in enumerate(rows):
            ut = set(nlp.tokens(idx.units[i]["text"])); scored = []
            for cid, ct in ctoks:
                if ct: scored.append((len(ct & ut) / len(ct), cid))
            tagged = [cid for s, cid in scored if s >= 0.6] or [cid for s, cid in sorted(scored, reverse=True)[:1] if s > 0]
            unit_tags.append((tid, sub_ids[sub[j]] if len(rows) >= 4 else None, json.dumps(tagged), idx.units[i]["id"]))
        db.many("UPDATE units SET topic_id=?, subtopic_id=?, concept_ids=? WHERE id=?", unit_tags)
    progress("Inferring prerequisites", 0.85)
    _prereqs(idx, topic_ids, topic_rows, use_ai)
    get_index(force=True)
    progress("Done", 1.0)
    return len(topic_ids)


def _prereqs(idx, topic_ids, topic_rows, use_ai=True):
    topics = db.q("SELECT * FROM topics WHERE parent_id IS NULL ORDER BY order_idx")
    edges = set()
    if use_ai and llm.enabled() and len(topics) > 1:
        listing = "\n".join(f"{t['id']}: {t['name']} - {t['summary']}" for t in topics)
        r = llm.chat_json("You are a curriculum designer.", f"Topics in teaching order:\n{listing}\n\nReturn JSON "
                          '{"prereqs": [[A,B],...]} where [A,B] means topic id A must be understood before topic id B. Only direct, '
                          "essential dependencies; max 2 prerequisites per topic.", max_tokens=800)
        if isinstance(r, dict):
            order = {t["id"]: t["order_idx"] for t in topics}
            for e in r.get("prereqs", []):
                try:
                    a, b = int(e[0]), int(e[1])
                    if a in order and b in order and order[a] < order[b]: edges.add((a, b))
                except Exception: pass
    if not edges:  # offline heuristic: term overlap with earlier topics, chain fallback
        cent = {t["id"]: np.asarray(idx.X[topic_rows[t["id"]]].mean(axis=0)).ravel() for t in topics}
        names = idx.tfidf.get_feature_names_out()
        tops = {tid: set(names[np.argsort(-v)[:12]]) for tid, v in cent.items()}
        for bi, b in enumerate(topics):
            txt = " ".join(idx.units[i]["text"] for i in topic_rows[b["id"]])
            bt = set(nlp.analyze(txt)); cand = []
            for a in topics[:bi]:
                ov = len(tops[a["id"]] & bt) / max(len(tops[a["id"]]), 1)
                cos = float(cent[a["id"]] @ cent[b["id"]] / (np.linalg.norm(cent[a["id"]]) * np.linalg.norm(cent[b["id"]]) + 1e-9))
                cand.append((ov + cos, a["id"]))
            cand.sort(reverse=True)
            for s, a in cand[:2]:
                if s >= 0.35: edges.add((a, b["id"]))
            if bi > 0 and not any(e[1] == b["id"] for e in edges):
                edges.add((cand[0][1], b["id"]))
    for a, b in edges: db.ex("INSERT INTO prereqs(topic_id,prereq_id) VALUES(?,?)", (b, a))
