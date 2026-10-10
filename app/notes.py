"""Customisable study notes from any source (lecture video / audio / PDF / slides).
LLM mode: map-reduce over timestamped segments following the learner's options. Offline mode: extractive notes."""
import json, math, re, time
from collections import Counter
from . import db, llm, nlp, lang as L
from .retrieval import get_index, cite

STYLES = {
    "key_points": ("Key points", "Only the most important ideas as short bullets under a few headings. No filler."),
    "summary": ("Summary", "A concise flowing summary written as short paragraphs."),
    "detailed": ("Detailed notes", "Thorough notes with headings, sub-bullets, definitions, examples, formulas and step-by-step reasoning. Cover everything that is taught."),
    "study_guide": ("Study guide", "Learning objectives, key terms with definitions, core concepts, worked examples, common mistakes, then 5 self-test questions with answers."),
    "qa": ("Question & answer", "Each important idea written as a question followed by a crisp answer."),
    "outline": ("Outline", "A clean hierarchical outline (numbered sections with nested bullets)."),
    "cheatsheet": ("Exam cheat-sheet", "A compact revision sheet: formulas, definitions, rules, mnemonics and things to remember. Extremely terse."),
}
LENGTHS = {"brief": ("Brief", "very short - roughly 5-8% of the original length", .07), "standard": ("Standard", "moderate - roughly 15-20% of the original length", .18),
           "comprehensive": ("Comprehensive", "long and complete - roughly 35-45% of the original length", .4),
           "detailed": ("Detailed (full)", "EXHAUSTIVE and fully explained - roughly 70-90% of the original length. Cover every concept, definition, example, formula, number and step that is taught. Explain in full sentences. Never compress, skip or merely list things", .8)}
DETAIL_RE = re.compile(r"\b(detail(?:ed|s)?|in[- ]depth|thorough(?:ly)?|comprehensive|exhaustive|elaborate|(?:proper|complete|full|long) notes)\b", re.I)
LEVELS = {"beginner": "Explain in simple words for a beginner; define jargon.", "intermediate": "Assume basic background knowledge.", "advanced": "Be technical and compact; assume strong background."}


def _segments(source_id):
    idx = get_index(); us = [u for u in idx.units if source_id is None or u["source_id"] == source_id]
    us.sort(key=lambda u: (u["source_id"], u["loc"].get("t0", u["seq"]) if u["kind"] in ("transcript", "figure") else u["seq"], u["seq"]))
    return us


def _tag(u, visuals):
    t = u["text"]
    if u["kind"] == "figure":
        if not visuals: return None
        t = "(On-screen visual) " + t
    return t


# ------------------------------------------------------------------ LLM path
def _chunks(segs, words=2600):
    out, cur, n = [], [], 0
    for s in segs:
        w = len(s[1].split())
        if cur and n + w > words: out.append(cur); cur, n = [], 0
        cur.append(s); n += w
    return out + ([cur] if cur else [])


def _llm_notes(segs, o, cb):
    st, ln = STYLES[o["style"]], LENGTHS[o["length"]]
    full = o["length"] == "detailed"
    chunks = _chunks(segs, 1200 if full else 2600); parts = []
    lang = L.prompt_name(o["language"])
    for ci, ch in enumerate(chunks):
        cb(f"Writing notes ({ci + 1}/{len(chunks)})", .15 + .7 * ci / len(chunks))
        ref = "Cite the segment ids like [T3] at the end of each bullet or paragraph they come from. " if o["timestamps"] else "Do not include segment ids. "
        sys_ = ("You are an expert note-taker turning a lecture/material into study notes. Use ONLY the provided material; never add outside facts. "
                f"Write in {lang}. Output clean Markdown (## headings, - bullets, **bold** for key terms). No tables. Use \\( ... \\) for inline formulas and \\[ ... \\] for display formulas; never emit bare LaTeX commands.")
        words = sum(len(s[1].split()) for s in ch)
        want = (f"TARGET: write about {int(words * ln[2])} words for this part (never fewer than {int(words * ln[2] * .8)}). For every concept give: a precise definition, a clear explanation in full sentences, an example from the material, and why it matters. Keep every formula, number, name and step. Do not summarise away detail.\n" if full else "")
        usr = (want + f"STYLE: {st[1]}\nLENGTH: {ln[1]} (this is part {ci + 1} of {len(chunks)} of the full material, so size it proportionally)\nAUDIENCE: {LEVELS[o['level']]}\n"
               + (f"USER'S SPECIAL INSTRUCTIONS (highest priority): {o['focus']}\n" if o["focus"] else "") + ref
               + ("Start with a '## ' heading for the topic of this part. " if len(chunks) > 1 else "Start with a '# ' title line. ")
               + "\n\nMATERIAL:\n" + "\n".join(f"[T{i + 1}] ({lab}) {txt}" for i, (_, txt, lab) in enumerate(ch)))
        try: txt = llm.chat(sys_, usr, max_tokens=9000 if full else 3500, temperature=.25)
        except Exception as e: raise RuntimeError(f"The AI provider failed while writing notes: {e}")
        txt = re.sub(r"\[T(\d+)\]", lambda m: f"[[U{ch[int(m.group(1)) - 1][0]}]]" if 0 < int(m.group(1)) <= len(ch) else "", txt)
        parts.append(txt.strip())
    body = "\n\n".join(parts)
    if len(parts) > 1 and o["style"] in ("summary", "key_points", "cheatsheet") or (len(parts) > 1 and o["length"] == "brief"):
        cb("Merging into one set of notes", .9)
        try:
            body = llm.chat("You merge partial study notes into one coherent set. Keep every [[U#]] marker attached to the point it supports; remove duplicates; keep the same Markdown style and language.",
                            f"STYLE: {st[1]}\nLENGTH: {ln[1]}\n" + (f"SPECIAL INSTRUCTIONS: {o['focus']}\n" if o["focus"] else "") + "\nPARTIAL NOTES:\n" + body, max_tokens=3500, temperature=.2).strip()
        except Exception: pass
    return body


# ------------------------------------------------------------------ offline path (extractive)
def _sents(segs):
    out = []
    for uid, txt, lab in segs:
        for s in nlp.sentences(re.sub(r"^(Speaker notes: )", "", txt)):
            if 3 <= len(s.split()) <= 60 and not s.startswith("["): out.append((uid, s.strip(), lab))
    return out


def _offline_notes(segs, o, cb):
    S = _sents(segs)
    if not S: raise ValueError("Nothing readable to summarise in this source.")
    toks = [nlp.tokens(s[1]) for s in S]; df = Counter(t for ts in toks for t in set(ts)); N = len(S)
    idf = {t: math.log(1 + N / c) for t, c in df.items()}
    ft = set(nlp.tokens(o["focus"])) if o["focus"] else set()
    sc = []
    for i, ts in enumerate(toks):
        if not ts: sc.append(0); continue
        v = sum(idf[t] for t in set(ts)) / (len(ts) ** .6)
        if ft: v *= 1 + 3 * len(ft & set(ts)) / len(ft)
        sc.append(v)
    ratio = LENGTHS[o["length"]][2]; k = max(3, min(N, round(N * ratio * (.6 if o["style"] in ("key_points", "cheatsheet") else 1))))
    pick = sorted(set(sorted(range(N), key=lambda i: -sc[i])[:k]) | {i for i in range(N) if re.search(r"\\(?:sqrt|frac|sum|int)|[=^]", S[i][1])})
    ref = lambda i: f" [[U{S[i][0]}]]" if o["timestamps"] else ""
    title = "# Study notes" + (f" — focus: {o['focus']}" if o["focus"] else "") + "\n"
    cb("Selecting the most important sentences", .6)
    # group picked sentences by source unit order into sections of ~6
    secs = [pick[i:i + 6] for i in range(0, len(pick), 6)]
    def head(ids):
        c = Counter(t for i in ids for t in toks[i]); words = [nlp.stem(w) for w, _ in c.most_common(3)]
        idx = get_index(); return " · ".join(idx.surface(w).title() for w in words) or "Section"
    st = o["style"]; out = [title]
    if st == "summary":
        for sec in secs: out.append(" ".join(S[i][1] for i in sec) + (ref(sec[-1]) if sec else "") + "\n")
    elif st in ("key_points", "cheatsheet"):
        for sec in secs: out.append(f"## {head(sec)}\n" + "\n".join(f"- {S[i][1]}{ref(i)}" for i in sec) + "\n")
    elif st == "qa":
        for i in pick:
            s = S[i][1]; ws = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]{4,}", s) if nlp.stem(w.lower()) in idf]
            if not ws: continue
            a = max(ws, key=lambda w: idf[nlp.stem(w.lower())])
            blank = re.sub(r"\b" + re.escape(a) + r"\b", "_____", s, count=1)
            out.append(f"**Q:** Complete the idea: “{blank}”\n**A:** {a}{ref(i)}\n")
    elif st == "study_guide":
        terms = [t for t, _ in sorted(idf.items(), key=lambda kv: -kv[1] * df[kv[0]])[:8]]; idx = get_index()
        out.append("## Key terms")
        for t in terms:
            j = next((i for i in range(N) if t in toks[i]), None)
            if j is not None: out.append(f"- **{idx.surface(t).title()}** — {S[j][1]}{ref(j)}")
        out.append("")
        for sec in secs: out.append(f"## {head(sec)}\n" + "\n".join(f"- {S[i][1]}{ref(i)}" for i in sec) + "\n")
    else:  # detailed / outline
        for n_, sec in enumerate(secs, 1):
            out.append(f"## {n_}. {head(sec)}\n" + "\n".join(f"- {S[i][1]}{ref(i)}" for i in sec) + "\n")
    if o["language"] != "en": out.append(f"\n> {L.LANGS[o['language']]['name']} notes need an AI key; these notes are in the language of the source.")
    return "\n".join(out)


# ------------------------------------------------------------------ public
def _grounding_footer(body, segs):
    """Lexical check of every sentence of the notes against the source text: unsupported sentences are flagged (never silently trusted)."""
    from . import grounding
    ctx = [{"text": t} for _, t, _ in segs]; ctxt = set()
    for u in ctx: ctxt.update(nlp.tokens(u["text"]))
    sents = [x for x in nlp.sentences(re.sub(r"\[\[U\d+\]\]|[#>*_`-]", " ", body)) if len(x.split()) >= 6]
    if not sents: return ""
    bad = [x for x in sents if (lambda t: t and sum(w in ctxt for w in t) / len(t) < grounding.MIN_SUPPORT)(nlp.tokens(x))]
    pct = round(100 * (1 - len(bad) / len(sents)))
    if not bad: return f"\n\n> Grounding check: {pct}% of sentences are traceable to the source."
    return f"\n\n> Grounding check: {pct}% of sentences are traceable to the source. {len(bad)} sentence(s) could not be matched and should be verified, e.g. “{bad[0][:140]}”"


def generate(source_id, options, cb=lambda m, p=None: None):
    o = {"style": options.get("style", "key_points"), "length": options.get("length", "standard"), "language": L.valid(options.get("language", "en")),
         "focus": (options.get("focus") or "").strip()[:500], "level": options.get("level", "intermediate"),
         "timestamps": bool(options.get("timestamps", True)), "visuals": bool(options.get("visuals", True))}
    if o["style"] not in STYLES: o["style"] = "key_points"
    if o["length"] not in LENGTHS: o["length"] = "standard"
    # the learner asked for proper/detailed notes (style "Detailed notes", or in their own words) -> really write detailed notes
    if DETAIL_RE.search(o["focus"]) or (o["style"] == "detailed" and o["length"] in ("standard", "comprehensive")): o["length"] = "detailed"
    if o["level"] not in LEVELS: o["level"] = "intermediate"
    cb("Reading the source", .05)
    segs = [(u["id"], t, u["label"]) for u in _segments(source_id) if (t := _tag(u, o["visuals"]))]
    if not segs: raise ValueError("This source has no readable content yet. Upload it in the Library first.")
    try:
        body = _llm_notes(segs, o, cb) if llm.enabled() else _offline_notes(segs, o, cb)
    except RuntimeError as e:  # AI provider down / out of quota: still deliver extractive notes instead of failing
        body = _offline_notes(segs, o, cb) + f"\n\n> The AI provider was unavailable ({str(e)[:160]}), so these notes were built by the offline extractive method."
    name = (db.q1("SELECT name FROM sources WHERE id=?", (source_id,)) or {"name": "All sources"})["name"]
    title = f"{STYLES[o['style']][0]} · {name}"
    if o["language"] == "en": body += _grounding_footer(body, segs)  # word-overlap check is only meaningful when notes are in the source language
    nid = db.ex("INSERT INTO notes(source_id,title,options,body,created) VALUES(?,?,?,?,?)", (source_id, title, json.dumps(o), body, time.time()))
    cb("Done", 1.0)
    return {"note_id": nid}


def view(nid):
    n = db.q1("SELECT * FROM notes WHERE id=?", (nid,))
    if not n: return None
    idx = get_index(); n["options"] = json.loads(n["options"])
    ids = {int(x) for x in re.findall(r"\[\[U(\d+)\]\]", n["body"])}
    n["cites"] = {str(i): cite(idx.by_id[i], 200) for i in ids if i in idx.by_id}
    return n


def to_markdown(n):
    lab = {k: c["label"] for k, c in n["cites"].items()}
    body = re.sub(r"\[\[U(\d+)\]\]", lambda m: f"*({lab.get(m.group(1), '')})*" if lab.get(m.group(1)) else "", n["body"])
    return body + f"\n\n---\n*Generated by StudyPilot · {n['title']}*\n"
