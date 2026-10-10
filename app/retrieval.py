"""Hybrid retrieval: BM25 + TF-IDF cosine (+ optional neural embeddings), fused with Reciprocal Rank Fusion."""
import json, math
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
from . import db, config as C, nlp

_caches = {}


class Index:
    def __init__(self):
        self.units = db.q("SELECT u.*, s.name AS source_name, s.kind AS source_kind FROM units u JOIN sources s ON s.id=u.source_id ORDER BY u.id")
        for u in self.units: u["loc"] = json.loads(u["loc"])
        self.n = len(self.units)
        self.by_id = {u["id"]: u for u in self.units}
        texts = [u["text"] for u in self.units] or ["empty"]
        self.tfidf = TfidfVectorizer(analyzer=nlp.analyze, sublinear_tf=True)
        self.X = self.tfidf.fit_transform(texts)
        self.cv = CountVectorizer(analyzer=nlp.tokens)
        self.C = self.cv.fit_transform(texts).tocsc()
        self.dl = np.asarray(self.C.sum(axis=1)).ravel(); self.avgdl = max(self.dl.mean(), 1)
        df = np.asarray((self.C > 0).sum(axis=0)).ravel()
        self.idf = np.log(1 + (self.n - df + 0.5) / (df + 0.5))
        self.vocab = self.cv.vocabulary_
        from collections import Counter, defaultdict
        self.surf = defaultdict(Counter)
        for u in self.units:
            for w in nlp.TOK.findall(u["text"].lower()):
                if w not in nlp.STOP and len(w) > 1: self.surf[nlp.stem(w)][w] += 1
        self.emb = None
        if C.EMBEDDINGS and self.n:
            try:
                from sentence_transformers import SentenceTransformer
                self.st = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
                self.emb = self.st.encode(texts, normalize_embeddings=True)
            except Exception as e:
                print("[retrieval] embeddings unavailable:", e)

    def surface(self, term):
        return " ".join(self.surf[p].most_common(1)[0][0] if p in self.surf else p for p in term.split("_"))

    def bm25(self, query, k1=1.4, b=0.75):
        sc = np.zeros(self.n)
        for t in set(nlp.tokens(query)):
            j = self.vocab.get(t)
            if j is None: continue
            col = self.C[:, j]; rows, tf = col.indices, col.data.astype(float)
            sc[rows] += self.idf[j] * tf * (k1 + 1) / (tf + k1 * (1 - b + b * self.dl[rows] / self.avgdl))
        return sc

    def search(self, query, k=6, topic_ids=None):
        if not self.n: return []
        cos = (self.X @ self.tfidf.transform([query]).T).toarray().ravel()
        bm = self.bm25(query)
        rankings = [np.argsort(-cos), np.argsort(-bm)]
        if self.emb is not None:
            dense = self.emb @ self.st.encode([query], normalize_embeddings=True)[0]
            rankings.append(np.argsort(-dense))
        fused = np.zeros(self.n)
        for r in rankings:
            for rank, i in enumerate(r[:50]): fused[i] += 1 / (60 + rank)
        order = np.argsort(-fused)
        out = []
        for i in order:
            u = self.units[i]
            if topic_ids and u["topic_id"] not in topic_ids: continue
            if cos[i] == 0 and bm[i] == 0: continue
            out.append({**u, "score": float(fused[i]), "cos": float(cos[i]), "bm25": float(bm[i])})
            if len(out) >= k: break
        return out

    def coverage(self, query, hits):
        """Fraction of the query's content terms found in the top retrieved units (off-topic detector)."""
        qt = set(nlp.tokens(query))
        if not qt: return 0.0
        ctx = set(t for h in hits[:4] for t in nlp.tokens(h["text"]))
        return len(qt & ctx) / len(qt)


def get_index(force=False):
    key = db.q1("SELECT COUNT(*) n, COALESCE(MAX(id),0) m, COALESCE(SUM(CASE WHEN topic_id IS NOT NULL THEN 1 ELSE 0 END),0) t FROM units")
    key = (key["n"], key["m"], key["t"]); cache = _caches.setdefault(str(C.DB_PATH), {"key": None, "idx": None})
    if force or cache["key"] != key:
        cache["idx"], cache["key"] = Index(), key
    return cache["idx"]


def cite(u, chars=260):
    return {"unit_id": u["id"], "source_id": u["source_id"], "source_name": u.get("source_name"), "kind": u.get("source_kind"),
            "unit_kind": u["kind"], "loc": u["loc"], "label": u["label"], "snippet": u["text"][:chars] + ("…" if len(u["text"]) > chars else "")}
