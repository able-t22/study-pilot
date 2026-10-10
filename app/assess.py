"""Adaptive assessment: generation (LLM or source concept checks), verification, novelty filter, grading, reports."""
import ast, json, math, operator, random, re, time
from . import db, llm, learner, nlp, config as C
from .retrieval import get_index, cite

QTYPES = ("mcq", "short", "numerical")
NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])")
norm = lambda s: re.sub(r"[^\w\u0900-\u097F]+", " ", str(s).lower()).strip()


# ------------------------------------------------------------------ safe numeric eval
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow,
        ast.USub: operator.neg, ast.Mod: operator.mod}
_FN = {"sqrt": math.sqrt, "log": math.log, "exp": math.exp, "ln": math.log, "log10": math.log10, "abs": abs, "round": round}


def safe_eval(expr):
    def ev(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)): return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS: return _OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS: return _OPS[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FN: return _FN[n.func.id](*[ev(a) for a in n.args])
        raise ValueError("unsafe")
    return float(ev(ast.parse(str(expr), mode="eval").body))


def to_float(s):
    try: return float(str(s).replace(",", "").strip())
    except Exception:
        m = NUM.search(str(s).replace(",", ""))
        return float(m.group()) if m else None


def num_close(a, b, tol=0.01):
    a, b = to_float(a), to_float(b)
    return a is not None and b is not None and abs(a - b) <= tol * max(abs(b), 1e-9) + 1e-9


# ------------------------------------------------------------------ offline cloze generator
def _words(text): return re.findall(r"[A-Za-z][A-Za-z\-]{4,}", text)


def _idf(idx, w):
    j = idx.vocab.get(nlp.stem(w.lower())); return float(idx.idf[j]) if j is not None else 0.0


CLOZE_STEMS = ("According to the course material, find the missing number", "Which term correctly completes this statement", "Fill in the missing key term")
_is_cloze = lambda stem: str(stem).startswith(CLOZE_STEMS)
_CODEY = re.compile(r"[*;=<>{}|\\_#@]|\b(SELECT|FROM|WHERE|GROUP BY|ORDER BY|INSERT|UPDATE|DELETE|JOIN|HAVING|def|import|return)\b|\bQ\d+\b|\bslide\b|https?://|\.(py|sql|pdf|png)\b", re.I)


def good_sentence(s):
    """A sentence worth turning into a question: real prose, not code, a heading, a question number or a fragment."""
    s = s.strip(); w = s.split()
    if not (8 <= len(w) <= 40) or not s[0].isupper() or s[-1] not in ".?!" or s.startswith("["): return False
    if re.search(r"\b(SELECT|FROM|WHERE|GROUP BY|ORDER BY|INSERT|UPDATE|DELETE|JOIN|HAVING)\b", s) or re.search(r"[*;=<>{}|\\_#@]|\bQ\d+\b|https?://", s): return False
    return sum(bool(re.fullmatch(r"[A-Za-z][A-Za-z\-']*[,.:;?!]?", x)) for x in w) / len(w) >= 0.7


def cloze_questions(idx, units, n, rng, types=("mcq", "short", "numerical"), topic_units=None):
    """Compatibility entry point: meaningful source concept checks, never random word blanks."""
    from .study_content import questions
    return questions(units, n, rng, types)


# ------------------------------------------------------------------ LLM generator + verification
GEN_SYS = ("You are an expert university exam-setter. Write questions answerable ONLY from the provided course excerpts, but phrased as standalone exam questions.\n"
           "RULES: (1) Test understanding - why/how/what-happens/which-is-correct/apply-to-a-case - never 'fill in a random word' or recall of a trivial detail. "
           "(2) The stem must make sense on its own: never write 'according to the passage/excerpt/course material', never mention [U#] ids, slide/page/question numbers. "
           "(3) MCQ: exactly 4 distinct, plausible options of similar length and kind; exactly one is correct; no 'all/none of the above'. "
           "(4) numerical: the answer must follow from numbers or code in the excerpt; include a calc expression. (5) short: test an explanation or comparison, with a concise reference answer. Use dollar-delimited inline math and double-dollar-delimited display math. "
           "(6) If an excerpt is mostly code or a table, ask what it does/returns/means, not to complete it. (7) Skip excerpts that are noise, headings or fragments.")
_BAD_STEM = re.compile(r"\[U\d+\]|\b(excerpt|passage|according to the (course|text|material))\b", re.I)


def llm_questions(units, specs, avoid):
    ctx = "\n\n".join(f"[U{u['id']}] ({u['source_name']} {u['label']})\n{u['text'][:1100]}" for u in units)
    spec = "\n".join(f"{i + 1}. type={s['type']}, difficulty={s['difficulty']}" for i, s in enumerate(specs))
    prompt = (f"EXCERPTS:\n{ctx}\n\nWrite {len(specs)} questions matching:\n{spec}\n\nAvoid duplicating these existing questions:\n" +
              "\n".join("- " + a[:120] for a in avoid[-15:]) +
              '\n\nReturn a JSON object with a questions list. Each item in questions: {"type":"mcq|short|numerical","difficulty":"easy|medium|hard","stem":"...",'
              '"options":["4 options, mcq only"],"answer":"for mcq the exact text of the correct option","explanation":"why, quoting the excerpt idea",'
              '"source_unit_id":<number from [U#]>,"misconceptions":{"<wrong option text>":"the misconception it reveals"} (mcq),'
              '"calc":"python arithmetic expression that computes the answer (numerical only)","tolerance":0.01,'
              '"keywords":["key terms a correct short answer must contain"] (short)}')
    r = llm.chat_json(GEN_SYS, prompt, max_tokens=4000)
    out = []
    items = r if isinstance(r, list) else next((v for v in r.values() if isinstance(v, list)), []) if isinstance(r, dict) else []
    for it in items:
        try:
            t = it["type"]; assert t in QTYPES and it["stem"] and it["answer"] is not None
            assert len(str(it["stem"])) >= 20 and not _BAD_STEM.search(str(it["stem"]))
            opts = it.get("options")
            if t == "mcq":
                assert isinstance(opts, list) and len(opts) == 4 and len({norm(o) for o in opts}) == len(opts)
                ans = next((o for o in opts if norm(o) == norm(it["answer"])), None)
                if ans is None and re.fullmatch(r"[A-Da-d]", str(it["answer"]).strip()): ans = opts["ABCD".index(str(it["answer"]).strip().upper())]
                assert ans is not None; random.shuffle(opts); it["answer"] = ans
            uid = int(re.sub(r"\D", "", str(it.get("source_unit_id", units[0]["id"]))) or units[0]["id"])
            if uid not in {u["id"] for u in units}: continue
            out.append(dict(qtype=t, stem=it["stem"], options=opts if t == "mcq" else None, answer=str(it["answer"]), explanation=it.get("explanation", ""),
                            unit_id=uid, difficulty=it.get("difficulty", "medium") if it.get("difficulty") in ("easy", "medium", "hard") else "medium",
                            extra={k: it[k] for k in ("misconceptions", "calc", "tolerance", "keywords") if k in it}))
        except Exception:
            continue
    return out


def verify(q, unit):
    """Return (ok, note). LLM mode: independent re-solve (optionally by a different model) + safe numeric check. Offline: extractive."""
    text = unit["text"]
    if q["qtype"] == "numerical" and q["extra"].get("calc"):
        try:
            if not num_close(safe_eval(q["extra"]["calc"]), q["answer"], 0.02): return False, "calc expression disagrees with key"
        except Exception:
            return False, "calc expression invalid"
    if _is_cloze(q["stem"]) or not llm.has_budget() or not llm.enabled(C.VERIFY_PROVIDER):
        ok = norm(q["answer"]) in norm(text) or q["qtype"] == "numerical" and to_float(q["answer"]) is not None and q["answer"] in text
        if q["qtype"] == "mcq": ok = ok and len(set(map(norm, q["options"]))) == len(q["options"]) and \
            sum(norm(o) in norm(q["stem"]) for o in q["options"]) == 0
        return ok, "extractive check: key found in source passage" if ok else "key not found in source"
    opts = ("\nOptions: " + " | ".join(q["options"])) if q["options"] else ""
    r = llm.chat_json("You are a careful student. Use ONLY the passage. If it does not support a single clear answer, set supported=false.",
                      f"PASSAGE:\n{text}\n\nQUESTION: {q['stem']}{opts}\n\nReturn JSON {{\"answer\":\"...\",\"supported\":true|false}}",
                      provider=C.VERIFY_PROVIDER, max_tokens=300)
    if r is None:  # verifier call itself failed (quota/network) -> fall back to the extractive check instead of rejecting everything
        ok = norm(q["answer"]) in norm(text) or (q["qtype"] == "numerical" and q["answer"] in text)
        return ok, "extractive check (AI verifier unavailable): key found in source" if ok else "key not found in source"
    if not isinstance(r, dict) or not r.get("supported", False): return False, "verifier: not supported by source"
    a, key = str(r.get("answer", "")), q["answer"]
    if q["qtype"] == "mcq":
        if re.fullmatch(r"[A-Da-d]", a.strip()): a = q["options"]["ABCD".index(a.strip().upper())]
        ok = norm(a) == norm(key) or norm(key) in norm(a)
    elif q["qtype"] == "numerical": ok = num_close(a, key, 0.02)
    else:
        kt, at = set(nlp.tokens(key)), set(nlp.tokens(a))
        ok = norm(a) == norm(key) or len(kt & at) / max(len(kt), 1) >= .6
    tag = "cross-model" if C.VERIFY_PROVIDER != C.PROVIDER else "self-consistency"
    return ok, f"{tag} verification: solver {'agrees' if ok else 'DISAGREES'}"


def grade_short(stem, key, resp, keywords=None, local=False):
    kt, rt = set(nlp.tokens(key)), set(nlp.tokens(resp))
    recall = len(kt & rt) / max(len(kt), 1)
    if recall >= .85: return True, recall, "Your answer covers the reference idea."
    if llm.enabled() and not local:
        r = llm.chat_json("You grade short answers strictly but fairly against a reference answer.",
                          f"Question: {stem}\nReference answer: {key}\nKey terms: {keywords}\nStudent answer: {resp}\n\nReturn JSON "
                          '{"score":0..1,"feedback":"one sentence: what is right/missing"}', max_tokens=250)
        if isinstance(r, dict) and "score" in r:
            return float(r["score"]) >= 0.7, float(r["score"]), r.get("feedback", "")
    kt = set(nlp.tokens(key)); rt = set(nlp.tokens(resp))
    rec = len(kt & rt) / max(len(kt), 1)
    return rec >= 0.6, rec, "" if rec >= 0.6 else f"Your answer is missing the key idea: “{key}”."


# ------------------------------------------------------------------ bank + generation
def _save(q, topic_id, subtopic_id, ok, note):
    return db.ex("INSERT INTO questions(qtype,stem,options,answer,explanation,topic_id,subtopic_id,unit_id,difficulty,verified,verify_note,extra,created) "
                 "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (q["qtype"], q["stem"], json.dumps(q["options"]) if q["options"] else None, q["answer"], q["explanation"],
                                                      topic_id, subtopic_id, q["unit_id"], q["difficulty"], int(ok), note, json.dumps(q["extra"]), time.time()))


def _hydrate(r):
    r["options"] = json.loads(r["options"]) if r["options"] else None; r["extra"] = json.loads(r["extra"] or "{}"); return r


def _is_dup(idx, stem, hist_vecs, thr=0.72):
    if hist_vecs is None: return False
    v = idx.tfidf.transform([stem]); sims = (hist_vecs @ v.T).toarray().ravel()
    return bool(sims.size and sims.max() >= thr)


def _history_vecs(idx, student_id):
    stems = [r["stem"] for r in db.q("SELECT DISTINCT q.stem FROM attempts a JOIN questions q ON q.id=a.question_id WHERE a.student_id=?", (student_id,))]
    return (idx.tfidf.transform(stems) if stems else None), stems


def _public(q, idx, topics):
    u = idx.by_id[q["unit_id"]]
    return {"id": q["id"], "qtype": q["qtype"], "stem": q["stem"], "options": q["options"], "difficulty": q["difficulty"],
            "topic_id": q["topic_id"], "topic": topics.get(q["topic_id"], ""), "source": cite(u), "verified": bool(q["verified"]), "verify_note": q["verify_note"]}


def start(student_id, topic_ids=None, n=10, types=None, kind="quiz", seed=None, progress=lambda m, p: None):
    # Share a budget across generation and verification, then complete locally.
    with llm.request_budget(C.QUIZ_AI_SECONDS):
        return _start(student_id, topic_ids, n, types, kind, seed, progress)


def _start(student_id, topic_ids=None, n=10, types=None, kind="quiz", seed=None, progress=lambda m, p: None):
    """kind: quiz | exam | adaptive | diagnostic"""
    if not db.q1("SELECT id FROM students WHERE id=?", (student_id,)): raise ValueError("Learner not found. Create a profile first.")
    n = max(1, min(int(n), 30))
    if kind not in ("quiz", "exam", "adaptive", "diagnostic", "mistakes"): raise ValueError("Unknown assessment mode")
    rng = random.Random(seed); idx = get_index()
    tops = learner.top_topics(); names = {t["id"]: t["name"] for t in tops}
    scope = [t for t in (topic_ids or [t["id"] for t in tops]) if t in names]
    if not scope: raise ValueError("Upload and analyse readable course material before starting practice.")
    mast = {m["topic_id"]: m for m in learner.get_mastery(student_id)}
    types = [t for t in (types or QTYPES) if t in QTYPES] or list(QTYPES)
    if kind == "mistakes":
        from .cockpit import mistakes
        rows = [r for r in mistakes(student_id) if r["topic_id"] in scope]
        chosen = [_hydrate(db.q1("SELECT * FROM questions WHERE id=?", (r["question_id"],))) for r in rows[:n]]
        if not chosen: raise ValueError("No unresolved mistakes in this scope. Try adaptive practice.")
        rng.shuffle(chosen)
        aid = db.ex("INSERT INTO assessments(student_id,kind,qids,before,created) VALUES(?,?,?,?,?)",
                    (student_id, kind, json.dumps([c["id"] for c in chosen]), json.dumps({str(k): v["p_eff"] for k, v in mast.items()}), time.time()))
        return {"assessment_id": aid, "kind": kind, "questions": [_public(c, idx, names) for c in chosen],
                "notice": "Retry your unresolved mistakes. Correct answers clear them from your mistake notebook."}
    if kind == "diagnostic":
        alloc = [t for t in scope for _ in range(max(1, math.ceil(n / max(len(scope), 1))))][:max(n, len(scope))]
    elif kind == "adaptive":
        alloc = learner.pick_topics({t: mast[t]["p_eff"] for t in scope}, {t: [p for p in ps if p in scope] for t, ps in learner.prereq_map().items()}, n, rng)
    else:
        alloc = [scope[i % len(scope)] for i in range(n)]; rng.shuffle(alloc)
    by_topic = {}
    for t in alloc:
        p = mast[t]["p_eff"]
        diff = "medium" if kind == "diagnostic" else rng.choices(["easy", "medium", "hard"], [.3, .5, .2])[0] if kind == "exam" else learner.target_difficulty(p)
        ty = "mcq" if kind == "diagnostic" and "mcq" in types else rng.choice(types)
        by_topic.setdefault(t, []).append({"type": ty, "difficulty": diff})
    chosen = prepare_batch(idx, student_id, by_topic, rng, n, progress)
    if not chosen:
        why = f" The AI provider reported: {llm.LAST_ERROR['msg']}" if llm.enabled() and llm.LAST_ERROR["msg"] else ""
        if llm.enabled(): raise ValueError("The AI could not write good questions right now (providers busy or rate-limited). Nothing low-quality was generated; please try again in a minute." + (" Last error: " + llm.LAST_ERROR["msg"][:160] if llm.LAST_ERROR["msg"] else ""))
        raise ValueError("Could not generate questions from this material. Make sure the uploaded files contain readable text (scanned PDFs need an AI key for OCR), or upload more material." + why)
    rng.shuffle(chosen)
    aid = db.ex("INSERT INTO assessments(student_id,kind,qids,before,created) VALUES(?,?,?,?,?)",
                (student_id, kind, json.dumps([c["id"] for c in chosen]), json.dumps({str(k): v["p_eff"] for k, v in mast.items()}), time.time()))
    fallback = any(c["extra"].get("local_concept") for c in chosen)
    return {"assessment_id": aid, "kind": kind, "questions": [_public(c, idx, names) for c in chosen],
            "requested": n, "notice": ("Previously practised questions are reused because this scope has limited fresh material. " if any(c["extra"].get("repeated_practice") for c in chosen) else "") + ("Source-based concept checks are included. Some MCQs may be replaced by written explanations when suitable distractors are unavailable. " if fallback else "") + (f"Prepared {len(chosen)} of {n} requested questions from the available material." if len(chosen) < n else "")}


def retake(assessment_id):
    """Same questions, brand-new attempt (own attempts + report). Mastery keeps learning from it like any other attempt."""
    a = db.q1("SELECT * FROM assessments WHERE id=?", (assessment_id,))
    if not a: raise ValueError("Quiz not found")
    idx = get_index(); names = {t["id"]: t["name"] for t in learner.top_topics()}
    qids = json.loads(a["qids"]); random.shuffle(qids)
    qs = [_hydrate(db.q1("SELECT * FROM questions WHERE id=?", (i,))) for i in qids]
    mast = {m["topic_id"]: m for m in learner.get_mastery(a["student_id"])}
    aid = db.ex("INSERT INTO assessments(student_id,kind,qids,before,created) VALUES(?,?,?,?,?)",
                (a["student_id"], a["kind"], json.dumps(qids), json.dumps({str(k): v["p_eff"] for k, v in mast.items()}), time.time()))
    return {"assessment_id": aid, "kind": a["kind"], "questions": [_public(q, idx, names) for q in qs]}


# ------------------------------------------------------------------ grading + report
def answer(assessment_id, qid, response):
    a = db.q1("SELECT * FROM assessments WHERE id=?", (assessment_id,))
    if not a: raise ValueError("Assessment not found")
    if a["finished"]: raise ValueError("This assessment is already finished")
    if qid not in json.loads(a["qids"]): raise ValueError("Question does not belong to this assessment")
    row = db.q1("SELECT * FROM questions WHERE id=?", (qid,))
    if not row: raise ValueError("Question no longer exists; start a new assessment")
    q = _hydrate(row)
    prev = db.q1("SELECT * FROM attempts WHERE assessment_id=? AND question_id=?", (assessment_id, qid))
    idx = get_index(); u = idx.by_id[q["unit_id"]]; fb = ""
    if prev: correct, score = bool(prev["correct"]), prev["score"]
    else:
        if q["qtype"] == "mcq": correct = norm(response) == norm(q["answer"]); score = float(correct)
        elif q["qtype"] == "numerical": correct = num_close(response, q["answer"], q["extra"].get("tolerance", 0.01)); score = float(correct)
        else:
            with llm.request_budget(10):
                correct, score, fb = grade_short(q["stem"], q["answer"], response, q["extra"].get("keywords"), q["extra"].get("local_concept", False))
        db.ex("INSERT INTO attempts(student_id,assessment_id,question_id,response,correct,score,ts) VALUES(?,?,?,?,?,?,?)",
              (a["student_id"], assessment_id, qid, str(response), int(correct), score, time.time()))
        learner.update(a["student_id"], q["topic_id"], correct, q["qtype"], q["difficulty"])
    mis = None
    if not correct:
        mis = (q["extra"].get("misconceptions") or {}).get(response) or (fb or None)
    return {"correct": correct, "score": score, "correct_answer": q["answer"], "explanation": q["explanation"], "feedback": fb,
            "misconception": mis, "citation": cite(u)}


def finish(assessment_id):
    a = db.q1("SELECT * FROM assessments WHERE id=?", (assessment_id,))
    if not a: raise ValueError("Assessment not found")
    if a["report"]: return json.loads(a["report"])
    idx = get_index(); names = {t["id"]: t["name"] for t in learner.top_topics()}
    rows = db.q("SELECT att.*, q.topic_id, q.qtype, q.stem, q.answer, q.unit_id, q.extra, q.difficulty FROM attempts att JOIN questions q ON q.id=att.question_id "
                "WHERE att.assessment_id=?", (assessment_id,))
    per = {}
    for r in rows:
        d = per.setdefault(r["topic_id"], {"topic_id": r["topic_id"], "topic": names.get(r["topic_id"]), "correct": 0, "total": 0})
        d["total"] += 1; d["correct"] += r["correct"]
    for d in per.values(): d["accuracy"] = round(d["correct"] / d["total"], 2)
    before = json.loads(a["before"]); after = {m["topic_id"]: m for m in learner.get_mastery(a["student_id"])}
    mis, review = [], []
    for r in rows:
        if r["correct"]: continue
        ex_ = json.loads(r["extra"] or "{}"); m = (ex_.get("misconceptions") or {}).get(r["response"])
        mis.append({"topic": names.get(r["topic_id"]), "question": r["stem"][:140], "your_answer": r["response"], "correct": r["answer"],
                    "likely_misconception": m or f"Missed the key idea “{r['answer']}”."})
        review.append(cite(idx.by_id[r["unit_id"]]))
    weak = sorted([d for d in per.values() if d["accuracy"] < 0.6], key=lambda d: d["accuracy"])
    rep = {"assessment_id": assessment_id, "kind": a["kind"], "score": sum(r["correct"] for r in rows), "total": len(rows),
           "per_topic": list(per.values()), "weak_topics": weak, "misconceptions": mis, "review_sources": review[:8],
           "mastery": [{"topic": names[t], "before": before.get(str(t)), "after": after[t]["p_eff"]} for t in per if t in after],
           "recommendations": learner.recommend(a["student_id"])}
    rep["narrative"] = f"You answered {rep['score']} of {rep['total']} correctly. Review the explanations for missed questions, then use targeted revision before trying again."
    db.ex("UPDATE assessments SET finished=?, report=? WHERE id=?", (time.time(), json.dumps(rep), assessment_id))
    return rep


def prepare_batch(idx, student_id, by_topic, rng, n, progress):
    """One generation request and one batch review, bounded across the whole quiz."""
    from .study_content import questions as concept_questions, numerical_questions
    hv, history = _history_vecs(idx, student_id)
    seen = {r["question_id"] for r in db.q("SELECT question_id FROM attempts WHERE student_id=?", (student_id,))}
    chosen=[]; missing=[]; used=set()
    for topic,specs in by_topic.items():
        bank=[_hydrate(r) for r in db.q("SELECT * FROM questions WHERE topic_id=? AND verified=1", (topic,))]
        for spec in specs:
            candidates=[q for q in bank if q["id"] not in seen and not _is_cloze(q["stem"]) and q["qtype"]==spec["type"] and norm(q["stem"]) not in used and not _is_dup(idx,q["stem"],hv)]
            if candidates:
                q=rng.choice(candidates);chosen.append(q);seen.add(q["id"]);used.add(norm(q["stem"]))
            else: missing.append(spec | {"topic_id":topic})
    units=[]
    for topic in by_topic:
        candidates=[u for u in idx.units if u["topic_id"]==topic and u["kind"]!="figure" and len(u["text"].split())>=5]
        rng.shuffle(candidates);units.extend(candidates[:3])
    progress("Preparing a single question batch", .15)
    generated=[]
    if missing and units and llm.enabled() and llm.has_budget():
        generated=llm_questions(units[:18],missing[:8],history)
    accepted=[]
    if generated and llm.has_budget():
        progress("Reviewing answers and source support", .6)
        review=llm.chat_json(
            "Independently solve and review each question using only its source. Reject ambiguous options, unsupported facts, incorrect answers, trivial word blanks, and meaningless questions.",
            json.dumps({"items":[{"id":i,"question":q["stem"],"options":q["options"],"source":idx.by_id[q["unit_id"]]["text"][:1800]} for i,q in enumerate(generated)]})+
            '\nReturn {"reviews":[{"id":0,"supported":true,"answer":"independently solved exact answer"}]}.',
            max_tokens=min(2200,200*len(generated)))
        reviews={int(x["id"]):x for x in (review or {}).get("reviews",[]) if isinstance(x,dict) and str(x.get("id","")).isdigit()} if isinstance(review,dict) else {}
        for i,q in enumerate(generated):
            r=reviews.get(i,{})
            if r.get("supported") is not True:continue
            answer=str(r.get("answer",""))
            if q["qtype"]=="numerical":
                try: ok=num_close(answer,q["answer"]) and num_close(safe_eval(q["extra"]["calc"]),q["answer"])
                except Exception:ok=False
            else:
                key=set(nlp.tokens(q["answer"]));sol=set(nlp.tokens(answer))
                ok=norm(answer)==norm(q["answer"]) or bool(key) and len(key&sol)/len(key)>=.8
            if ok:accepted.append((q,"Batch review: independent answer agrees with source"))
    # Local concept questions also cover failed requests and small batches without extra API calls.
    accepted.extend((q,"Source concept check: answer taken directly from cited sentence")
                    for q in concept_questions(units,max(n*3,20),rng,tuple({s["type"] for specs in by_topic.values() for s in specs})))
    accepted.extend((q,"Source formula applied: arithmetic independently checked") for q in numerical_questions(units,n,rng,tuple({s["type"] for specs in by_topic.values() for s in specs})))
    progress("Finishing source-backed practice",.85)
    for q,note in accepted:
        if len(chosen)>=n:break
        if norm(q["stem"]) in used or (not q["extra"].get("local_calculation") and _is_dup(idx,q["stem"],hv)):continue
        u=idx.by_id[q["unit_id"]]
        if u["topic_id"] not in by_topic:continue
        if sum(x["topic_id"] == u["topic_id"] for x in chosen) >= len(by_topic[u["topic_id"]]): continue
        qid=_save(q,u["topic_id"],u["subtopic_id"],True,note)
        q.update(id=qid,topic_id=u["topic_id"],subtopic_id=u["subtopic_id"],verified=1,verify_note=note)
        chosen.append(q);used.add(norm(q["stem"]))
    if len(chosen) < n:
        for topic in by_topic:
            for row in db.q("SELECT * FROM questions WHERE topic_id=? AND verified=1 ORDER BY id DESC", (topic,)):
                if len(chosen) >= n: break
                q=_hydrate(row)
                if _is_cloze(q["stem"]) or norm(q["stem"]) in used: continue
                q["extra"]["repeated_practice"] = True
                chosen.append(q);used.add(norm(q["stem"]))
    return chosen

