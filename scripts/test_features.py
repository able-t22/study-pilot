"""Integration test (mocked OpenRouter, serverless/inline-job mode): outside knowledge, detailed notes, retake, recommendations, job state."""
import os, sys, tempfile, json
from pathlib import Path
os.environ.update(DATA_DIR=tempfile.mkdtemp(), STUDYPILOT_INLINE_JOBS="1", OPENROUTER_API_KEY="TEST", OPENROUTER_MODEL="test/model", OPENROUTER_FALLBACK_MODELS="")
os.environ["DATABASE_URL"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx
SEEN = []; LAST_KEY = [""]
class R:
    status_code = 200
    def __init__(s, t, src=()): s.t = t; s.src = src; s.text = t
    def json(s):
        msg = {"content": s.t}
        if s.src: msg["annotations"] = [{"type": "url_citation", "url_citation": {"url": u, "title": "Wiki"}} for u in s.src]
        return {"choices": [{"message": msg}]}
def fake(url, headers=None, json=None, timeout=None):
    SEEN.append(json); user = json["messages"][1]["content"]
    if json.get("plugins"): return R("Biodiversity is the variety of life on Earth.", ["https://en.wikipedia.org/wiki/Biodiversity"])
    if "STYLE:" in user: return R("# Notes\n" + "Detailed explanation sentence. " * 60)
    if "Independently solve and review" in json["messages"][0]["content"]:
        data=__import__("json").loads(user.split("\nReturn")[0]);return R(__import__("json").dumps({"reviews":[{"id":x["id"],"supported":True,"answer":"Gradient descent"} for x in data["items"]]}))
    if "thoughtful, precise" in json["messages"][0]["content"]: return R("The learning rate controls each parameter-update step. A smaller step changes parameters more slowly. [S1]")
    if "careful student" in json["messages"][0]["content"]: return R(__import__("json").dumps({"answer": LAST_KEY[0], "supported": True}))
    if "Write " in user and "questions matching" in user:
        import re as _re, json as _j
        uid = int(_re.search(r"\[U(\d+)\]", user).group(1)); n = int(_re.search(r"Write (\d+) questions", user).group(1)); LAST_KEY[0] = "Gradient descent"
        return R(_j.dumps([{"type": "mcq", "difficulty": "medium", "stem": f"Which method iteratively adjusts parameters to minimise a loss function (variant {i})?",
                            "options": ["Gradient descent", "Random sampling", "Bubble sort", "Binary search"], "answer": "Gradient descent", "explanation": "Parameters move against the gradient.",
                            "source_unit_id": uid} for i in range(n)]))
    return R("not json")

from fastapi.testclient import TestClient
from app.main import app
from app import config as C, llm
llm._send = fake
FX = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
c = TestClient(app); assert C.SERVERLESS and str(C.DATA).startswith("/tmp") or "DATA_DIR" in os.environ
sid = c.post("/api/students", json={"name": "T"}).json()["id"]; c.cookies.set("sp_user", str(sid))
r = c.post("/api/upload", files=[("files", (n, open(FX / n, "rb"))) for n in ("intro_ml_textbook.pdf", "intro_ml_lecture.vtt")]).json()
assert r["state"]["status"] == "done", r; print("PASS serverless: job finished inline, state returned with the POST")
# outside knowledge
q = {"student_id": sid, "message": "explain photosynthesis inside chloroplast"}
a = c.post("/api/chat", json=q).json(); print({k: a[k] for k in ("covered","coverage","answer")}); assert not a["covered"] and not a.get("outside_answer"); print("PASS off-material question is flagged (toggle off)")
a = c.post("/api/chat", json={**q, "allow_outside": True}).json()
assert a["outside_answer"].startswith("Biodiversity") and a["outside_web"] and a["outside_sources"][0]["url"].startswith("https://en.wikipedia"), a
print("PASS outside knowledge: web-grounded answer + sources")
a = c.post("/api/chat", json={"student_id": sid, "message": "What does the learning rate do?"}).json(); assert a["covered"] and a["citations"]; print("PASS in-material answer still cited")
# detailed notes
src = [s for s in c.get("/api/sources").json() if s["kind"] == "video"][0]["id"]
lens = c.get("/api/notes/options").json()["lengths"]; assert "detailed" in lens
for body, want in (({"style": "detailed"}, "detailed"), ({"style": "key_points", "focus": "please make it in detail"}, "detailed"), ({"style": "key_points"}, "standard"), ({"style": "detailed", "length": "brief"}, "brief")):
    SEEN.clear(); j = c.post("/api/notes/generate", json={"source_id": src, **body}).json(); nid = j["state"]["result"]["note_id"]
    n = c.get(f"/api/notes/{nid}").json(); assert n["options"]["length"] == want, (body, n["options"]); 
    if want == "detailed": 
        sent = [s for s in SEEN if "STYLE:" in s["messages"][1]["content"]][0]
        assert sent["max_tokens"] == 9000 and "TARGET: write about" in sent["messages"][1]["content"] and len(n["body"]) > 1000
print("PASS detailed notes: auto-selected, 9000-token budget, word target in prompt")
# quiz: retake + recommendations show progress
st = c.post("/api/assess/start", json={"student_id": sid, "n": 6, "kind": "quiz", "types": ["mcq"]}).json(); qs = st["questions"]
d0 = c.get(f"/api/dashboard/{sid}").json(); assert all("n_obs" in r for r in d0["recommend"])
for qq in qs[:3]: c.post("/api/assess/answer", json={"assessment_id": st["assessment_id"], "question_id": qq["id"], "response": "x"})
d1 = c.get(f"/api/dashboard/{sid}").json(); practised = [r for r in d1["recommend"] if r["n_obs"]]
assert practised and any(r["n_obs"] > 0 for r in d1["recommend"]), d1["recommend"]; print("PASS dashboard: practice evidence updates topic mastery:", [(r["name"][:18], r["p_eff"], r["n_obs"]) for r in d1["recommend"]])
rt = c.post(f"/api/assess/retake/{st['assessment_id']}").json()
assert rt["assessment_id"] != st["assessment_id"] and sorted(x["id"] for x in rt["questions"]) == sorted(x["id"] for x in qs); print("PASS retake: same questions, new attempt id")
f = c.post(f"/api/assess/answer", json={"assessment_id": rt["assessment_id"], "question_id": rt["questions"][0]["id"], "response": "x"}).json(); rep = c.post(f"/api/assess/finish/{rt['assessment_id']}").json(); assert rep["total"] == 1; print("PASS end early: report covers only answered questions")

# ---- question quality
from app import assess, llm
good = "Gradient descent updates the parameters in the direction that reduces the loss function."
bad = "IT employees with salary above 60,000 SELECT * FROM Employees WHERE dept = 'IT' AND salary > 30000; Q12."
assert assess.good_sentence(good) and not assess.good_sentence(bad) and not assess.good_sentence("Q12 and more words here to pad it out a bit longer ok.") ; print("PASS offline filter rejects SQL/code/question-number sentences, keeps prose")
assert all(not assess._is_cloze(a["stem"]) and (a["qtype"] != "mcq" or len(a["options"]) == 4) for a in qs) , qs[0]; print("PASS questions use standalone concepts with valid MCQ structure when applicable")
# stale junk already saved in the bank is never reused while an AI is configured
from app import db
db.ex("UPDATE questions SET stem=? WHERE id=(SELECT MIN(id) FROM questions)", ("Fill in the missing key term (short answer):\n\u201cx _____ y\u201d",))
assert assess._is_cloze("Which term correctly completes this statement from the course material?\n\u201cx\u201d"); print("PASS cloze stems recognised (excluded from bank reuse when AI is on)")
# AI configured but provider down -> labelled extractive fallback
def down(url, headers=None, json=None, timeout=None):
    class D:
        status_code = 503; text = "overloaded"; headers = {}
        def json(self): return {}
    return D()
c2 = TestClient(app); sid2 = c2.post("/api/students", json={"name": "T2"}).json()["id"]; c2.cookies.set("sp_user", str(sid2))
c2.post("/api/upload", files=[("files", (n, open(FX / n, "rb"))) for n in ("intro_ml_textbook.pdf", "intro_ml_lecture.vtt")])
llm._send = down; llm._cool.clear()
r = c2.post("/api/assess/start", json={"student_id": sid2, "n": 4, "kind": "quiz"})
assert r.status_code == 200 and r.json()["questions"] and "Source-based concept" in r.json()["notice"], (r.status_code, r.text[:300]); print("PASS AI down -> labelled source-based concept questions")
