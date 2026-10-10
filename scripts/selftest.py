"""Smoke test: per-learner isolation, ingestion, notes, tutor, quiz (no API key needed). Uses tests/fixtures (developer-only files)."""
import sys, time, shutil, os, tempfile
from pathlib import Path
os.environ["DATA_DIR"] = tempfile.mkdtemp()
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["DATABASE_URL"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient
from app.main import app
FX = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
c = TestClient(app)


def wait(j):
    while (s := c.get(f"/api/jobs/{j}").json())["status"] == "running": time.sleep(0.3)
    assert s["status"] == "done", s
    return s


a = c.post("/api/students", json={"name": "A"}).json()["id"]; b = c.post("/api/students", json={"name": "B"}).json()["id"]
c.cookies.set("sp_user", str(a))
files = [("files", (n, open(FX / n, "rb"))) for n in ("intro_ml_textbook.pdf", "intro_ml_lecture.vtt")]
wait(c.post("/api/upload", files=files).json()["job"])
ov = c.get("/api/overview").json(); assert ov["topics"] and ov["tagged"], ov
src = [s for s in c.get("/api/sources").json() if s["kind"] == "video"][0]["id"]
for style in ("key_points", "detailed", "qa", "study_guide", "summary"):
    for ln in ("brief", "comprehensive"):
        nid = wait(c.post("/api/notes/generate", json={"source_id": src, "style": style, "length": ln, "focus": "learning rate"}).json()["job"])["result"]["note_id"]
        n = c.get(f"/api/notes/{nid}").json(); assert len(n["body"]) > 80, (style, ln)
assert c.get(f"/api/notes/{nid}/download").status_code == 200
assert c.post("/api/chat", json={"student_id": a, "message": "What does the learning rate do?"}).json()["covered"]
q = c.post("/api/assess/start", json={"student_id": a, "n": 6, "kind": "quiz"}).json(); assert q["questions"], q
c.cookies.set("sp_user", str(b))   # brand-new learner sees NOTHING
assert c.get("/api/sources").json() == [] and c.get("/api/graph").json()["topics"] == [] and c.get("/api/notes").json() == []
print("SELFTEST OK:", len(q["questions"]), "questions; isolation verified")
