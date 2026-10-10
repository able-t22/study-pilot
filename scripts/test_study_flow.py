"""Regression coverage for reported study-flow failures; no live provider calls."""
import json, os, sys, tempfile, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
os.environ.update(DATA_DIR=tempfile.mkdtemp(), DATABASE_URL="", OPENROUTER_API_KEY="TEST", OPENROUTER_MODEL="test/model", OPENROUTER_FALLBACK_MODELS="", STUDYPILOT_INLINE_JOBS="1")
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient
from app.main import app
from app import llm, config as C, db, learner
c=TestClient(app)
sid=c.post("/api/students",json={"name":"Regression"}).json()["id"]
c.cookies.set("sp_user",str(sid))
source=("Gradient descent updates the parameters in the direction that reduces the loss function. "
"The learning rate controls the size of each parameter update during training. "
"Precision measures the fraction of predicted positives that are correct. "
"Recall measures the fraction of actual positives that are detected. "
"Accuracy measures the fraction of predictions that are correct. "
"A square root is a value which produces the original number when multiplied by itself. "
"The root formula is \\(x=\\sqrt{n}\\).")
j=c.post("/api/upload",files={"files":("course.txt",source)}).json()
assert j["state"]["status"]=="done",j
calls=[]
class Reply:
    status_code=200
    headers={}
    text=""
    def __init__(self,body): self.body=body
    def json(self):return {"choices":[{"message":{"content":self.body}}]}
def success(url,**kw):
    p=kw["json"];calls.append(p);system,user=[x["content"] for x in p["messages"]]
    if "exam-setter" in system:
        import re
        uid=int(re.search(r"\[U(\d+)\]",user).group(1))
        return Reply(json.dumps({"questions":[{"type":"short","difficulty":"medium","stem":"How does the learning rate affect each parameter update?","answer":"It controls the size of each parameter update.","explanation":"The learning rate sets the update step size.","source_unit_id":uid}]}))
    if "Independently solve" in system:
        return Reply(json.dumps({"reviews":[{"id":0,"supported":True,"answer":"It controls the size of each parameter update."}]}))
    if "thoughtful" in system:return Reply("The learning rate controls how far the parameters move during each update. Smaller steps change them more gradually. [S1]")
    return Reply("OK")
llm._send=success
r=c.post("/api/chat",json={"student_id":sid,"message":"How does the learning rate affect training?","lang":"auto"}).json()
assert r["mode"]=="ai_explanation" and r["citations"],r
assert len(calls)==1, "English tutor must not translate first"
calls.clear()
q=c.post("/api/assess/start",json={"student_id":sid,"n":4,"types":["short"]}).json()
assert q.get("questions"),q
assert len(calls)==2, f"Expected one generation and one batch review, got {len(calls)}"
assert not any("____" in x["stem"] for x in q["questions"])
# Revision must load even with a configured key and failing network.
def down(*a,**k):
    calls.append("outage")
    raise llm.httpx.ConnectError("simulated outage")
llm._send=down;llm._cool.clear();calls.clear()
rev=c.get(f"/api/revision/{sid}").json()
assert rev and rev[0]["flashcards"] and rev[0]["slides"],rev
assert not calls,"Revision must not wait for provider calls"
C.CURRENT_USER.set(sid)
for m in learner.get_mastery(sid):
    db.ex("UPDATE mastery SET p_know=.99 WHERE student_id=? AND topic_id=?",(sid,m["topic_id"]))
assert c.get(f"/api/revision/{sid}").json(),"Strong topics must also have revision content"
llm._cool.clear()
r=c.post("/api/chat",json={"student_id":sid,"message":"What does the learning rate control?"}).json()
assert r["mode"]=="source_excerpts" and r.get("ai_error") and "could not complete" in r["answer"],r
llm._cool.clear();calls.clear();t=time.monotonic()
q=c.post("/api/assess/start",json={"student_id":sid,"n":4,"types":["numerical"]}).json()
assert q.get("questions") and all(x["qtype"]=="numerical" for x in q["questions"]),q
assert time.monotonic()-t<5 and len(calls)<=1
note=c.post("/api/notes/generate",json={"source_id":1,"style":"detailed","length":"detailed"}).json()
assert note["state"]["status"]=="done",note
body=c.get("/api/notes/"+str(note["state"]["result"]["note_id"])).json()["body"]
assert r"\sqrt{n}" in body,"Detailed fallback notes must preserve formulas"
status=c.get("/api/config").json()
assert status["ai"]["status"]=="error" and "TEST" not in json.dumps(status)
assert llm.parse_json(r'{"answer":"\frac{1}{2} + \sqrt{4}"}')["answer"]==r"\frac{1}{2} + \sqrt{4}"
# Concurrent first-load requests should not race PRAGMA journal_mode.
def read(_):
    C.CURRENT_USER.set(999)
    return db.q("SELECT COUNT(*) n FROM units")
with ThreadPoolExecutor(max_workers=8) as pool:
    assert all(x==[{"n":0}] for x in pool.map(read,range(16)))
print("STUDY FLOW REGRESSIONS OK: one-call tutor, batched quiz, outage fallback, immediate revision, maths and concurrent startup")
