"""Upload, question recovery, cockpit, mistake retry and workspace regression checks."""
import os, sys, tempfile, json, time
from pathlib import Path
os.environ.update(DATA_DIR=tempfile.mkdtemp(), STUDYPILOT_INLINE_JOBS="1", OPENROUTER_API_KEY="", DATABASE_URL="")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient
from app.main import app
from app import db, config as C, llm, ingest
c = TestClient(app)
sid = c.post("/api/students", json={"name": "Regression", "goal": "Understand machine learning"}).json()["id"]
c.cookies.set("sp_user", str(sid))
empty = c.post("/api/assess/start", json={"student_id": sid})
assert empty.status_code == 400 and "Upload and analyse" in empty.text
assert c.post("/api/upload", files={"files": ("bad.exe", b"bad")}).status_code == 400
assert c.post("/api/upload", files={"files": ("empty.txt", b"")}).status_code == 400
assert c.post("/api/upload", files=[("files", ("same.txt", b"a")), ("files", ("same.txt", b"b"))]).status_code == 400
assert c.post("/api/upload", files=[("files", ("CASE.txt", b"a")), ("files", ("case.txt", b"b"))]).status_code == 400
# Fast upload never invokes AI, yet builds topics and citations.
original = llm.chat_json
def forbidden(*a, **kw): raise AssertionError("Fast upload called AI")
llm.chat_json = forbidden
fx = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
with open(fx / "intro_ml_textbook.pdf", "rb") as f:
    result = c.post("/api/upload", files={"files": ("book.pdf", f)}).json()
assert result["state"]["status"] == "done", result
assert result["state"]["result"]["fast"] is True
llm.chat_json = original
search = c.get("/api/search", params={"q": "gradient descent"}).json()["results"]
assert search and search[0]["source_id"] and search[0]["loc"]
assert c.get("/api/search", params={"q": "gradient", "source_id": 999999}).json()["results"] == []
assert c.get("/api/search").json()["results"] == []
cockpit = c.get(f"/api/cockpit/{sid}").json()
assert cockpit["practised"] == 0 and cockpit["mastery"] is None and cockpit["mistakes"] == []
job = c.post("/api/assess/start-job", json={"student_id": sid, "n": 4, "types": ["mcq"]}).json()
assert job["state"]["status"] == "done", job
quiz = job["state"]["result"]
assert quiz["questions"] and quiz["notice"]
question = quiz["questions"][0]
body = {"assessment_id": quiz["assessment_id"], "question_id": question["id"], "response": "wrong answer"}
assert c.post("/api/assess/answer", json=body).status_code == 200
wrong = c.get(f"/api/cockpit/{sid}").json()
assert wrong["practised"] > 0 and len(wrong["mistakes"]) == 1
retry = c.post("/api/assess/start", json={"student_id": sid, "kind": "mistakes"}).json()
assert [q["id"] for q in retry["questions"]] == [question["id"]]
body.update(assessment_id=retry["assessment_id"], response=wrong["mistakes"][0]["answer"])
assert c.post("/api/assess/answer", json=body).json()["correct"]
assert c.get(f"/api/cockpit/{sid}").json()["mistakes"] == []
assert c.post("/api/assess/start", json={"student_id": sid, "kind": "mistakes"}).status_code == 400
assert c.post(f"/api/assess/finish/{retry['assessment_id']}").status_code == 200
assert c.post("/api/assess/answer", json=body).status_code == 400
body.update(assessment_id=quiz["assessment_id"], question_id=999999)
assert c.post("/api/assess/answer", json=body).status_code == 400
assert c.post("/api/assess/finish/999999").status_code == 404
# Same filename cannot overwrite the original uploaded source.
C.CURRENT_USER.set(sid)
old_path = Path(db.q1("SELECT path FROM sources LIMIT 1")["path"])
old_bytes = old_path.read_bytes()
text = b"Gradient descent adjusts parameters to reduce the loss function. The learning rate controls the size of each update step."
r = c.post("/api/upload", files={"files": ("book.txt", text)})
assert r.json()["state"]["status"] == "done"
r2 = c.post("/api/upload", files={"files": ("book.txt", text)})
assert r2.json()["state"]["status"] == "done"
paths = [r["path"] for r in db.q("SELECT path FROM sources WHERE name='book.txt'")]
assert len(paths) == 2 and paths[0] != paths[1] and old_path.read_bytes() == old_bytes
# A second learner cannot poll the first learner's jobs or see source search results.
other = c.post("/api/students", json={"name": "Other"}).json()["id"]
c.cookies.set("sp_user", str(other))
assert c.get("/api/jobs/" + job["job"]).status_code == 404
assert c.get("/api/search", params={"q": "gradient"}).json()["results"] == []
print("REPAIR REGRESSIONS OK")
