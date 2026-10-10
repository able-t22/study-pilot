"""Targeted revision material for weak topics: flashcards, slide deck (+ .pptx export) and a spoken audio brief.
Everything is built only from the learner's uploaded material; every card / bullet / sentence is checked by app.grounding and dropped if unsupported."""
import io, re, random
from . import db, llm, learner, assess, grounding, nlp, lang as L
from .retrieval import get_index, cite


def _units(topic_id, idx, min_words=3):
    return [u for u in idx.units if u["topic_id"] == topic_id and u["kind"] != "figure" and len(u["text"].split()) >= min_words]


def _best_sentences(idx, units, k, avoid=()):
    """Highest-information, well-formed sentences (no code / fragments), each with its unit."""
    seen, scored = set(avoid), []
    for u in units:
        for s in nlp.sentences(re.sub(r"^(Speaker notes: )", "", u["text"])):
            if len(s.split()) < 3 or s in seen: continue
            seen.add(s); ws = assess._words(s)
            scored.append((sum(assess._idf(idx, w) for w in ws) / (len(ws) + 3), s, u))
    scored.sort(key=lambda x: -x[0]); return [(s, u) for _, s, u in scored[:k]]


def flashcards(topic_id, n=8, seed=1, lang="en"):
    """-> (cards, dropped). Each card: front, back, source (page/slide/timestamp), grounded=True."""
    idx = get_index(); units = _units(topic_id, idx)
    if not units: return [], 0
    cards = []
    if llm.enabled() and llm.has_budget():
        ctx = "\n\n".join(f"[U{u['id']}] {u['text'][:700]}" for u in units[:8])
        r = llm.chat_json("You make concise study flashcards strictly from the excerpts. Never add facts that are not in them.",
                          f"{ctx}\n\nCreate {n} flashcards as a JSON list "
                          '[{"front":"question or term","back":"answer, at most 30 words, using only the excerpts","source_unit_id":N}]' +
                          (f". Write front and back in {L.prompt_name(lang)}, keeping technical terms in English in brackets." if lang != "en" else ""), max_tokens=1800)
        for c in (r if isinstance(r, list) else r.get("cards", r.get("flashcards", [])) if isinstance(r, dict) else []):
            try: u = idx.by_id[int(re.sub(r"\D", "", str(c["source_unit_id"])))]; cards.append((str(c["front"]), str(c["back"]), u))
            except Exception: pass
    if not cards:  # no AI (or unusable reply): concept -> the source sentence that defines/uses it
        from .study_content import facts
        used = set()
        for fact in facts(units)[:n]:
            cards.append((f"Explain {fact['subject']}.", fact['sentence'], fact['unit']))
            used.add(fact['sentence'])
        rng = random.Random(seed)

        concepts = [r["name"] for r in db.q("SELECT name FROM concepts WHERE topic_id=?", (topic_id,))]; rng.shuffle(concepts)
        for name in concepts:
            if len(cards) >= n: break
            nt = set(nlp.tokens(name))
            if not nt: continue
            best = next(iter(sorted(((s, u) for s, u in _best_sentences(idx, units, 60, used) if nt <= set(nlp.tokens(s))), key=lambda x: len(x[0]))), None)
            if best: used.add(best[0]); cards.append((f"What does your material say about “{name}”?", best[0], best[1]))
            if len(cards) >= n: break
        for s, u in _best_sentences(idx, units, n - len(cards), used):
            cards.append(("Recall this key idea from " + u["label"] + ":", s, u))
    ok = grounding.verify([b for _, b, _ in cards], units, lexical=(lang == "en")) if cards else []
    out = [{"front": f, "back": b, "source": cite(u), "grounded": True} for (f, b, u), k in zip(cards, ok) if k]
    return out[:n], sum(1 for k in ok if not k)


def _short(s, n=30):
    w = s.split(); return s if len(w) <= n else " ".join(w[:n]).rstrip(",;:") + "…"


def slides(topic_id, max_slides=5, lang="en"):
    """-> (slides, dropped_bullets). Each slide: title, bullets[], source."""
    idx = get_index(); units = _units(topic_id, idx, 8)
    if not units: return [], 0
    t = db.q1("SELECT name FROM topics WHERE id=?", (topic_id,)); out, dropped = [], 0
    if llm.enabled() and llm.has_budget():
        ctx = "\n\n".join(f"[U{u['id']}] {u['text'][:700]}" for u in units[:8])
        r = llm.chat_json("You build clear revision slides strictly from the excerpts. Never add facts that are not in them.",
                          f"TOPIC: {t['name']}\n{ctx}\n\nCreate {max_slides} slides as JSON "
                          '[{"title":"short title","bullets":["3-4 bullets, each <= 22 words, using only the excerpts"],"source_unit_id":N}]' +
                          (f". Write in {L.prompt_name(lang)}, keeping technical terms in English in brackets." if lang != "en" else ""), max_tokens=2200)
        for sl in (r if isinstance(r, list) else []):
            try:
                u = idx.by_id[int(re.sub(r"\D", "", str(sl["source_unit_id"])))]; bl = [str(b) for b in sl["bullets"]][:4]
                ok = grounding.verify(bl, [u] + units[:4], lexical=(lang == "en")); dropped += ok.count(False)
                bl = [b for b, k in zip(bl, ok) if k]
                if bl: out.append({"title": str(sl["title"])[:80], "bullets": bl, "source": cite(u)})
            except Exception: pass
    if not out:  # offline: one slide per sub-topic from its most informative well-formed sentences
        subs = {}
        for u in units: subs.setdefault(u["subtopic_id"], []).append(u)
        for sid_, us in list(subs.items())[:max_slides]:
            st = db.q1("SELECT name FROM topics WHERE id=?", (sid_,)) if sid_ and sid_ != topic_id else None
            picks = [(s, u) for s, u in _best_sentences(idx, us, 6) if len(s.split()) <= 32][:3]
            if picks: out.append({"title": (st or t)["name"][:80], "bullets": [s for s, _ in picks], "source": cite(picks[0][1])})
    return out[:max_slides], dropped


def brief(topic_id, lang="en"):
    """-> (script, grounding_pct). Spoken-style brief; sentences the material does not support are removed."""
    t = db.q1("SELECT * FROM topics WHERE id=?", (topic_id,)); idx = get_index(); units = _units(topic_id, idx, 6)[:8]
    src = " ".join(u["text"][:500] for u in units)
    if llm.enabled():
        try:
            txt = llm.chat("You write 60-second spoken revision briefs using ONLY the material given. Add no outside facts.",
                           f"Topic: {t['name']}\nMaterial:\n{src}\n\nWrite a clear spoken-style brief (~140 words), no markdown, in {L.prompt_name(lang)}.", max_tokens=600)
            g = grounding.ground_text(txt, units, lexical=(lang == "en"))
            if g["text"].strip(): return g["text"], g["pct"]
        except Exception: pass
    picks = [s for s, _ in _best_sentences(idx, units, 5)]
    return f"Revision brief on {t['name']}. " + " ".join(picks or nlp.sentences(src)[:4]), 1.0


def for_student(sid, max_topics=3, lang="en"):
    # Revision must remain immediately available even when the provider is unavailable.
    with llm.request_budget(0):
        return _for_student(sid, max_topics, lang)

def _for_student(sid, max_topics=3, lang="en"):
    lang = L.valid(lang)
    weak = sorted(learner.get_mastery(sid), key=lambda m: m["p_eff"])[:max_topics]; out = []
    for m in weak:
        cards, dc = flashcards(m["topic_id"], 6, lang=lang); sl, ds = slides(m["topic_id"], lang=lang); b, pct = brief(m["topic_id"], lang)
        srcs = list(dict.fromkeys(((c["source"] or {}).get("source_name", "") + " · " + (c["source"] or {}).get("label", "")) for c in cards + sl))[:8]
        out.append({"topic_id": m["topic_id"], "topic": m["name"], "p_eff": m["p_eff"], "flashcards": cards, "slides": sl, "audio_brief": b, "lang": lang,
                    "grounding": {"cards_dropped": dc, "bullets_dropped": ds, "brief_supported_pct": pct}, "sources": srcs})
    return out


def pptx_bytes(sid, topic_ids=None, lang="en"):
    """Weak-topic revision deck as a .pptx (title slide, content slides with source footers, sources slide)."""
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    st = db.q1("SELECT name FROM students WHERE id=?", (sid,)); data = for_student(sid, 3, lang) if not topic_ids else None
    if topic_ids:
        mm = {m["topic_id"]: m for m in learner.get_mastery(sid)}
        data = [{"topic": mm[t]["name"], "p_eff": mm[t]["p_eff"], "slides": slides(t, lang=lang)[0], "sources": []} for t in topic_ids if t in mm]
    prs = Presentation(); prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    ink, acc, mut = RGBColor(0x1e, 0x1b, 0x4b), RGBColor(0x7c, 0x83, 0xff), RGBColor(0x64, 0x6b, 0x8a)

    def textbox(sl, x, y, w, h, text, size, bold=False, color=ink):
        tf = sl.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)).text_frame; tf.word_wrap = True
        p = tf.paragraphs[0]; p.text = text; p.font.size = Pt(size); p.font.bold = bold; p.font.color.rgb = color; return tf

    s0 = prs.slides.add_slide(prs.slide_layouts[6])
    textbox(s0, 0.8, 2.4, 11.5, 1.2, "Targeted revision deck", 44, True); textbox(s0, 0.8, 3.7, 11.5, 0.8, f"Prepared for {st['name'] if st else 'learner'} · weak topics only", 22, False, mut)
    textbox(s0, 0.8, 6.6, 11.5, 0.5, "Built only from your uploaded material. Every bullet carries its source.", 14, False, mut)
    for tp in data:
        for sl in tp["slides"]:
            s = prs.slides.add_slide(prs.slide_layouts[6])
            textbox(s, 0.8, 0.5, 11.7, 0.5, f"{tp['topic']}  ·  mastery {round(tp['p_eff'] * 100)}%", 14, False, acc)
            textbox(s, 0.8, 1.0, 11.7, 1.0, sl["title"], 34, True)
            tf = textbox(s, 0.9, 2.2, 11.5, 4.2, "• " + sl["bullets"][0], 22)
            for b in sl["bullets"][1:]:
                p = tf.add_paragraph(); p.text = "• " + b; p.font.size = Pt(22); p.font.color.rgb = ink; p.space_before = Pt(14)
            src = sl.get("source") or {}; textbox(s, 0.8, 6.8, 11.7, 0.4, f"Source: {src.get('source_name', '')} · {src.get('label', '')}", 12, False, mut)
    if not data or not any(tp["slides"] for tp in data):
        s = prs.slides.add_slide(prs.slide_layouts[6]); textbox(s, 0.8, 3.0, 11.7, 1.0, "No weak topics with enough material yet.", 30, True)
    buf = io.BytesIO(); prs.save(buf); return buf.getvalue()
