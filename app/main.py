import contextvars, json, shutil, threading, time, traceback, uuid
from pathlib import Path
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from . import config as C, db, ingest, kb, learner, tutor, assess, revision, evals, simulate, llm, notes, users, intake, audit, fw_eval, srs, podcast, teachback, glossary, lang as L
from .retrieval import get_index, cite

async def _who(request: Request):
    """Every API call runs inside the workspace of the learner named in the sp_user cookie."""
    try: uid = int(request.cookies.get("sp_user", 0))
    except ValueError: uid = 0
    C.CURRENT_USER.set(uid if users.get(uid) else 0)


app = FastAPI(title="StudyPilot", dependencies=[Depends(_who)])
STATIC = C.ROOT / "static"
JOBS = {}


def job(fn, *a):
    jid = uuid.uuid4().hex[:8]; JOBS[jid] = {"owner": C.CURRENT_USER.get(), "status": "running", "msg": "starting", "pct": 0, "result": None}

    def cb(msg, pct=None):
        JOBS[jid]["msg"] = msg
        if pct is not None: JOBS[jid]["pct"] = round(pct, 2)

    def run():
        try: JOBS[jid]["result"] = fn(*a, cb); JOBS[jid]["status"] = "done"; JOBS[jid]["pct"] = 1
        except Exception as e:
            traceback.print_exc(); JOBS[jid].update(status="error", msg=str(e))
    if C.SERVERLESS: run()  # serverless functions freeze after responding, so no background threads: run inline (state is returned with the response)
    else:
        ctx = contextvars.copy_context()
        threading.Thread(target=lambda: ctx.run(run), daemon=True).start()
    return jid


def jr(jid):
    """Job response. Serverless instances do not share memory, so the finished state travels with the response instead of being polled."""
    return {"job": jid, "state": JOBS[jid] if C.SERVERLESS else None}


@app.post("/api/ai/test")
def test_ai():
    return llm.diagnostics(probe=True)

@app.get("/api/config")
def config():
    return {"provider": C.PROVIDER, "llm": llm.enabled(), "vision": llm.vision_enabled(), "verify_provider": C.VERIFY_PROVIDER,
            "fallback": llm.chain()[1:] if llm.enabled() else [], "last_provider": llm.STATE["last_provider"], "last_model": llm.STATE.get("last_model"), "serverless": C.SERVERLESS,
            "ai": llm.diagnostics(), "llm_error": llm.LAST_ERROR["msg"], "embeddings": C.EMBEDDINGS, "mode": "LLM-powered" if llm.enabled() else "local study (no API key: source excerpts and concept questions)"}


@app.get("/api/jobs/{jid}")
def jobs(jid: str):
    if jid not in JOBS or JOBS[jid]["owner"] != C.CURRENT_USER.get(): raise HTTPException(404)
    j = JOBS[jid]; return {k: (v if k != "result" else (v if isinstance(v, (dict, list, int, str, type(None))) else None)) for k, v in j.items()}


# ---------------- library
def _ingest_many(paths, fast, cb):
    ingest.FAST_INGEST.set(fast)
    media_stems = {p.stem.lower() for p in paths if p.suffix.lower() in ingest.VIDEO | ingest.AUDIO}
    paths = [p for p in paths if not (p.suffix.lower() in (".vtt", ".srt") and p.stem.lower() in media_stems)]
    ids = []
    for i, p in enumerate(paths):
        ids.append(ingest.ingest_file(p, cb=lambda m, pct, i=i: cb(f"[{i + 1}/{len(paths)}] {Path(p).name}: {m}", (i + (pct or 0)) / (len(paths) + 1))))
    cb("Analysing course structure (topics, concepts, prerequisites)...", len(paths) / (len(paths) + 1))
    n = kb.build(lambda m, p: cb("Analysing: " + m, (len(paths) + p) / (len(paths) + 1)), use_ai=not fast)
    return {"sources": ids, "topics": n, "fast": fast}


@app.post("/api/upload")
def upload(files: list[UploadFile] = File(...), fast: bool = Form(True)):
    # Run disk I/O in FastAPI's worker pool rather than blocking the event loop.
    allowed = ingest.VIDEO | ingest.AUDIO | {".pdf", ".pptx", ".txt", ".md", ".vtt", ".srt"}
    if not files or any(Path(f.filename or "").suffix.lower() not in allowed for f in files):
        raise HTTPException(400, "Choose a supported PDF, PPTX, text, transcript, audio or video file.")
    names = [Path((f.filename or "").replace("\\", "/")).name for f in files]
    if len(names) != len({name.casefold() for name in names}): raise HTTPException(400, "Files in a batch must have distinct names.")
    batch = C.UPLOADS / uuid.uuid4().hex
    batch.mkdir()
    paths = []
    try:
        for f, name in zip(files, names):
            dest = batch / name
            with open(dest, "wb") as out: shutil.copyfileobj(f.file, out, length=1024 * 1024)
            if not dest.stat().st_size: raise HTTPException(400, "Cannot upload empty files.")
            paths.append(dest)
    except Exception:
        shutil.rmtree(batch)
        raise
    return jr(job(_ingest_many, paths, fast))


@app.post("/api/analyze")
def analyze():
    return jr(job(lambda cb: {"topics": kb.build(cb)}))


@app.get("/api/sources")
def sources():
    return db.q("SELECT s.id,s.name,s.kind,(SELECT COUNT(*) FROM units u WHERE u.source_id=s.id) units FROM sources s ORDER BY s.id")


@app.delete("/api/sources/{sid}")
def del_source(sid: int):
    db.ex("DELETE FROM units WHERE source_id=?", (sid,)); db.ex("DELETE FROM sources WHERE id=?", (sid,))
    db.reset_analysis(); return {"ok": True, "note": "Delete done. Click Re-analyse to rebuild topics."}


@app.get("/api/graph")
def graph(student_id: int | None = None):
    tops = db.q("SELECT * FROM topics ORDER BY parent_id IS NOT NULL, order_idx")
    m = {x["topic_id"]: x for x in learner.get_mastery(student_id)} if student_id and tops else {}
    nu = {r["topic_id"]: r["n"] for r in db.q("SELECT topic_id, COUNT(*) n FROM units GROUP BY topic_id")}
    for t in tops:
        t["units"] = nu.get(t["id"], 0)
        if t["id"] in m: t["p_eff"] = m[t["id"]]["p_eff"]
    return {"topics": tops, "concepts": db.q("SELECT * FROM concepts"), "prereqs": db.q("SELECT * FROM prereqs")}


@app.get("/api/units")
def units(topic_id: int):
    idx = get_index(); return [cite(u, 500) for u in idx.units if u["topic_id"] == topic_id or u["subtopic_id"] == topic_id]


# ---------------- source viewer
@app.get("/api/source/{sid}/info")
def src_info(sid: int):
    s = db.q1("SELECT * FROM sources WHERE id=?", (sid,))
    if not s: raise HTTPException(404)
    meta = json.loads(s["meta"] or "{}"); return {"id": sid, "name": s["name"], "kind": s["kind"], "has_video": bool(meta.get("media")),
                                                  "has_pdf": s["kind"] == "pdf" or bool(meta.get("pdf"))}


@app.get("/api/source/{sid}/page/{n}.png")
def src_page(sid: int, n: int, q: str = ""):
    import fitz
    s = db.q1("SELECT * FROM sources WHERE id=?", (sid,)); meta = json.loads(s["meta"] or "{}")
    path = s["path"] if s["kind"] == "pdf" else meta.get("pdf")
    if not path: raise HTTPException(404)
    doc = fitz.open(path); page = doc[max(0, min(n - 1, len(doc) - 1))]
    for frag in [x for x in q.split("|") if len(x) > 8][:3]:
        for r in page.search_for(frag[:60]): page.add_highlight_annot(r)
    return Response(page.get_pixmap(dpi=100).tobytes("png"), media_type="image/png")


@app.get("/api/source/{sid}/media")
def src_media(sid: int):
    s = db.q1("SELECT * FROM sources WHERE id=?", (sid,)); meta = json.loads(s["meta"] or "{}")
    if not meta.get("media"): raise HTTPException(404)
    return FileResponse(meta["media"])


@app.get("/api/source/{sid}/slide/{n}")
def src_slide(sid: int, n: int):
    idx = get_index(); us = [u for u in idx.units if u["source_id"] == sid and u["loc"].get("slide") == n]
    imgs = [f.name for f in C.MEDIA.glob(f"s{sid}_sl{n}_*.png")]
    return {"units": [cite(u, 2000) for u in us], "images": imgs}


@app.get("/api/media/{name}")
def media(name: str):
    p = C.MEDIA / Path(name).name
    if not p.exists(): raise HTTPException(404)
    return FileResponse(p)


@app.get("/api/overview")
def overview():
    kinds = {r["kind"]: r["n"] for r in db.q("SELECT kind, COUNT(*) n FROM units GROUP BY kind")}
    srcs = {r["kind"]: r["n"] for r in db.q("SELECT kind, COUNT(*) n FROM sources GROUP BY kind")}
    qs = db.q1("SELECT COUNT(*) n, COALESCE(SUM(verified),0) v FROM questions")
    return {"sources": srcs, "units": kinds, "topics": db.q1("SELECT COUNT(*) n FROM topics WHERE parent_id IS NULL")["n"],
            "subtopics": db.q1("SELECT COUNT(*) n FROM topics WHERE parent_id IS NOT NULL")["n"], "concepts": db.q1("SELECT COUNT(*) n FROM concepts")["n"],
            "prereqs": db.q1("SELECT COUNT(*) n FROM prereqs")["n"], "questions": qs["n"], "verified": qs["v"],
            "tagged": db.q1("SELECT COUNT(*) n FROM units WHERE topic_id IS NOT NULL")["n"], "students": db.q1("SELECT COUNT(*) n FROM students")["n"]}


@app.get("/api/report/{aid}", response_class=HTMLResponse)
def report_html(aid: int):
    """Printable post-assessment report (Ctrl/Cmd+P -> Save as PDF)."""
    from html import escape as e
    a = db.q1("SELECT * FROM assessments WHERE id=?", (aid,))
    if not a or not a["report"]: raise HTTPException(404, "Finish the assessment first")
    r = json.loads(a["report"]); st = db.q1("SELECT name FROM students WHERE id=?", (a["student_id"],)) or {"name": ""}
    row = lambda *c: "<tr>" + "".join(f"<td>{e(str(x))}</td>" for x in c) + "</tr>"
    html = f"""<!doctype html><meta charset=utf-8><title>StudyPilot report #{aid}</title><style>body{{font:15px/1.55 Inter,system-ui,sans-serif;max-width:820px;margin:40px auto;color:#14182b;padding:0 20px}}
h1{{margin:0}}h2{{margin-top:28px;border-bottom:2px solid #e3e7f5;padding-bottom:6px}}.big{{font-size:44px;font-weight:800;color:#5b5bf0}}table{{width:100%;border-collapse:collapse}}td,th{{padding:7px 8px;border-bottom:1px solid #e3e7f5;text-align:left}}.m{{background:#fff4f4;border-left:3px solid #ef5b72;padding:8px 12px;margin:8px 0;border-radius:6px}}</style>
<h1>StudyPilot · Assessment report</h1><p>{e(st['name'])} · {e(a['kind'])} · assessment #{aid}</p><div class=big>{r['score']}/{r['total']}</div><p>{e(r.get('narrative',''))}</p>
<h2>Per-topic accuracy</h2><table><tr><th>Topic</th><th>Correct</th><th>Accuracy</th></tr>{''.join(row(t['topic'], f"{t['correct']}/{t['total']}", f"{round(t['accuracy']*100)}%") for t in r['per_topic'])}</table>
<h2>Weak topics</h2>{''.join(f"<p>⚠ {e(w['topic'])} - {w['correct']}/{w['total']}</p>" for w in r['weak_topics']) or '<p>None</p>'}
<h2>Likely misconceptions</h2>{''.join(f"<div class=m><b>{e(m['topic'])}</b>: {e(m['likely_misconception'])}<br><small>Q: {e(m['question'])} · answered “{e(m['your_answer'])}”, correct “{e(m['correct'])}”</small></div>" for m in r['misconceptions']) or '<p>None detected</p>'}
<h2>Review in your material</h2><ul>{''.join(f"<li>{e(c.get('source_name',''))} · {e(c.get('label',''))}</li>" for c in r['review_sources'])}</ul>
<h2>Recommended next</h2><ul>{''.join(f"<li><b>{e(x['name'])}</b> - {e(x['reason'])}</li>" for x in r['recommendations'])}</ul>"""
    return HTMLResponse(html)


# ---------------- students / learner
class StudentIn(BaseModel):
    name: str
    level: str = "beginner"
    goal: str = ""
    exam_date: str = ""


@app.post("/api/students")
def new_student(s: StudentIn):
    if not s.name.strip(): raise HTTPException(400, "Name required")
    uid = users.create(s.name, s.level, s.goal, s.exam_date)
    token = C.CURRENT_USER.set(uid)
    try: db.init(); learner.init_student(s.name.strip(), s.level, s.goal, s.exam_date, sid=uid)
    finally: C.CURRENT_USER.reset(token)
    return {"id": uid}


@app.get("/api/students")
def students():
    return users.list_users()


@app.delete("/api/students/{uid}")
def del_student(uid: int):
    users.delete(uid); return {"ok": True}


@app.get("/api/dashboard/{sid}")
def dashboard(sid: int):
    hist = db.q("SELECT a.kind, a.created, a.finished, a.report FROM assessments a WHERE a.student_id=? AND a.report IS NOT NULL ORDER BY a.id", (sid,))
    h = []
    for r in hist:
        rep = json.loads(r["report"]); h.append({"kind": r["kind"], "ts": r["finished"], "score": rep["score"], "total": rep["total"]})
    st = db.q1("SELECT * FROM students WHERE id=?", (sid,))
    return {"student": st, "intake": intake.get(sid), "reviews": srs.stats(sid), "mastery": learner.get_mastery(sid), "recommend": learner.recommend(sid), "history": h, "trajectory": learner.trajectory(sid),
            "attempts": db.q1("SELECT COUNT(*) n, COALESCE(SUM(correct),0) c FROM attempts WHERE student_id=?", (sid,))}


@app.get("/api/schedule/{sid}")
def schedule(sid: int, days: int = 7, minutes: int = 90):
    return learner.schedule(sid, max(1, min(days, 60)), max(30, minutes))


@app.get("/api/revision/{sid}")
def rev(sid: int, lang: str = "en", n: int = 3):
    return revision.for_student(sid, max_topics=max(1, min(n, 8)), lang=lang)


# ---------------- tutor + assessment
class ChatIn(BaseModel):
    student_id: int | None = None
    message: str
    lang: str = "en"
    allow_outside: bool = False
    history: list[dict] = []
    style: str = "standard"


@app.get("/api/revision/{sid}/slides.pptx")
def rev_pptx(sid: int, topics: str = "", lang: str = "en"):
    ids = [int(x) for x in topics.split(",") if x.strip().isdigit()] or None
    data = revision.pptx_bytes(sid, ids, L.valid(lang))
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation", headers={"Content-Disposition": 'attachment; filename="revision-deck.pptx"'})


class IntakeIn(BaseModel):
    goal: str = ""
    level: str = "beginner"
    exam_date: str = ""
    minutes_per_day: int = 45
    self_rating: dict = {}
    notes: str = ""


@app.get("/api/intake/{sid}")
def intake_get(sid: int):
    return {**intake.get(sid), "topics": [{"id": t["id"], "name": t["name"]} for t in learner.top_topics()], "attempts": db.q1("SELECT COUNT(*) n FROM attempts WHERE student_id=?", (sid,))["n"]}


@app.post("/api/intake/{sid}")
def intake_post(sid: int, b: IntakeIn):
    if not db.q1("SELECT id FROM students WHERE id=?", (sid,)): raise HTTPException(404, "Learner not found")
    return intake.apply(sid, b.model_dump())


class ReviewBuild(BaseModel):
    topics: list = []
    per_topic: int = 8
    lang: str = "en"


class Grade(BaseModel):
    id: int
    grade: str


class PodIn(BaseModel):
    topics: list = []
    lang: str = "en"


class TBIn(BaseModel):
    topic_id: int
    text: str
    lang: str = "en"


@app.post("/api/review/{sid}/build")
def review_build(sid: int, b: ReviewBuild):
    return srs.build(sid, [int(x) for x in b.topics] or None, max(2, min(b.per_topic, 20)), L.valid(b.lang))


@app.get("/api/review/{sid}/due")
def review_due(sid: int):
    return {"cards": srs.due(sid), **srs.stats(sid)}


@app.post("/api/review/{sid}/grade")
def review_grade(sid: int, b: Grade):
    try: return srs.grade(sid, b.id, b.grade)
    except ValueError as e: raise HTTPException(404, str(e))


@app.get("/api/export/{sid}/anki.tsv")
def export_anki(sid: int):
    return Response(srs.anki_tsv(sid), media_type="text/tab-separated-values", headers={"Content-Disposition": 'attachment; filename="studypilot-anki.tsv"'})


@app.post("/api/podcast/{sid}")
def podcast_build(sid: int, b: PodIn):
    try: return podcast.build(sid, [int(x) for x in b.topics], b.lang)
    except ValueError as e: raise HTTPException(400, str(e))


@app.post("/api/teachback/{sid}")
def teachback_check(sid: int, b: TBIn):
    try: return teachback.check(sid, b.topic_id, b.text, L.valid(b.lang))
    except ValueError as e: raise HTTPException(400, str(e))


@app.get("/api/teachback/{sid}/history")
def teachback_history(sid: int):
    return teachback.history(sid)


@app.get("/api/glossary")
def glossary_get():
    return glossary.build()


@app.get("/api/languages")
def languages():
    from . import lang
    return {k: {"name": v["name"], "native": v["native"], "speech": v["speech"]} for k, v in lang.LANGS.items()}


@app.post("/api/chat")
def chat(c: ChatIn):
    return tutor.answer(c.student_id, c.message, c.lang, c.history, c.allow_outside, style=c.style)


class StartIn(BaseModel):
    student_id: int
    topic_ids: list[int] = []
    n: int = 8
    types: list[str] = []
    kind: str = "quiz"


@app.post("/api/assess/start")
def a_start(s: StartIn):
    try: return assess.start(s.student_id, s.topic_ids or None, s.n, s.types or None, s.kind)
    except ValueError as e: raise HTTPException(400, str(e))


@app.post("/api/assess/start-job")
def a_start_job(s: StartIn):
    def prepare(cb):
        return assess.start(s.student_id, s.topic_ids or None, s.n, s.types or None, s.kind, progress=cb)
    return jr(job(prepare))


class AnsIn(BaseModel):
    assessment_id: int
    question_id: int
    response: str


@app.post("/api/assess/answer")
def a_answer(a: AnsIn):
    try: return assess.answer(a.assessment_id, a.question_id, a.response)
    except ValueError as e: raise HTTPException(400, str(e))


@app.post("/api/assess/retake/{aid}")
def a_retake(aid: int):
    try: return assess.retake(aid)
    except ValueError as e: raise HTTPException(404, str(e))


@app.post("/api/assess/finish/{aid}")
def a_finish(aid: int):
    try: return assess.finish(aid)
    except ValueError as e: raise HTTPException(404, str(e))


# ---------------- notes
class NotesIn(BaseModel):
    source_id: int | None = None
    style: str = "key_points"
    length: str = "standard"
    language: str = "en"
    level: str = "intermediate"
    focus: str = ""
    timestamps: bool = True
    visuals: bool = True


@app.get("/api/notes/options")
def notes_options():
    return {"styles": {k: {"name": v[0], "desc": v[1]} for k, v in notes.STYLES.items()}, "lengths": {k: v[0] for k, v in notes.LENGTHS.items()}}


@app.post("/api/notes/generate")
def notes_generate(n: NotesIn):
    return jr(job(lambda o, cb: notes.generate(o.source_id, o.model_dump(), cb), n))


@app.get("/api/notes")
def notes_list():
    return db.q("SELECT id, source_id, title, options, created FROM notes ORDER BY id DESC")


@app.get("/api/notes/{nid}")
def notes_get(nid: int):
    n = notes.view(nid)
    if not n: raise HTTPException(404)
    return n


@app.get("/api/notes/{nid}/download")
def notes_dl(nid: int):
    n = notes.view(nid)
    if not n: raise HTTPException(404)
    name = "".join(c if c.isalnum() else "_" for c in n["title"])[:60] or "notes"
    return Response(notes.to_markdown(n), media_type="text/markdown", headers={"Content-Disposition": f'attachment; filename="{name}.md"'})


@app.delete("/api/notes/{nid}")
def notes_del(nid: int):
    db.ex("DELETE FROM notes WHERE id=?", (nid,)); return {"ok": True}


# ---------------- evaluation
@app.post("/api/eval/rag")
def eval_rag(n: int = 20):
    return jr(job(lambda n, cb: {"metrics": evals.run(n, cb)["metrics"]}, n))


@app.post("/api/eval/sim")
def eval_sim(students: int = 30):
    return jr(job(lambda n, cb: {"ok": bool(simulate.run(n, progress=cb))}, students))


@app.post("/api/eval/audit")
def eval_audit():
    return audit.run()


@app.post("/api/eval/framework")
def eval_framework(n: int = 10):
    return jr(job(lambda n, cb: {"metrics": fw_eval.run(n, cb)["metrics"]}, max(3, min(n, 40))))


@app.get("/api/eval/results")
def eval_results():
    out = {}
    for k, f in (("rag", "rag_eval.json"), ("sim", "sim_eval.json"), ("audit", "audit.json"), ("deepeval", "deepeval.json")):
        p = C.EVAL / f; out[k] = json.loads(p.read_text()) if p.exists() else None
    return out


# ---------------- study cockpit / source search
@app.get("/api/cockpit/{sid}")
def cockpit_overview(sid: int):
    from . import cockpit
    try: return cockpit.overview(sid)
    except ValueError as e: raise HTTPException(404, str(e))


@app.get("/api/search")
def source_search(q: str = "", source_id: int | None = None):
    if not q.strip(): return {"results": []}
    idx = get_index()
    hits = idx.search(q[:500], k=idx.n if source_id else 12)
    if source_id: hits = [h for h in hits if h["source_id"] == source_id][:12]
    return {"results": [cite(h, 600) for h in hits]}


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
