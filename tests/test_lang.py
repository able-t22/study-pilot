"""Language tests with a mocked LLM (no key needed): answer language is independent of question language."""
import os, sys, tempfile, time, json
from pathlib import Path
os.environ["DATA_DIR"] = tempfile.mkdtemp(); sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient
from app.main import app
from app import llm, tutor, lang as L
FX = Path(__file__).resolve().parent / "fixtures"; c = TestClient(app)
uid = c.post("/api/students", json={"name": "T"}).json()["id"]; c.cookies.set("sp_user", str(uid))
j = c.post("/api/upload", files=[("files", (n, open(FX / n, "rb"))) for n in ("intro_ml_textbook.pdf", "intro_ml_lecture.vtt")]).json()["job"]
while c.get(f"/api/jobs/{j}").json()["status"] == "running": time.sleep(.3)
SEEN = []
def fake_json(system, user, **kw):
    SEEN.append(user)
    if "translate student questions" in system:
        q = user.split("Question: ")[1].split("\n")[0]
        if "கற்றல் வீதம்" in q or "kya hota" in q: return {"english": "What does the learning rate do?", "lang": "ta" if "கற்றல்" in q else "hi"}
        return {"english": q, "lang": "en"}
    return {"covered": False, "answer": "x"} if "FORCE_REFUSE" in user else {"covered": True, "answer": "[S1] ok", "check_question": "q?"}
def fake_chat(system,user,**kw):
    SEEN.append(user)
    return "[S1] ok"
llm.enabled = lambda *a, **k: True; llm.chat_json = fake_json; llm.chat = fake_chat
tutor.llm = llm
def ask(q, lang): return c.post("/api/chat", json={"student_id": uid, "message": q, "lang": lang}).json()
r = ask("What does the learning rate do?", "hi"); assert r["covered"] and r["lang"] == "hi", r      # the reported bug
assert "Hindi (Devanagari script)" in SEEN[-1]
r = ask("கற்றல் வீதம் என்ன செய்கிறது?", "auto"); assert r["covered"] and r["lang"] == "ta" and r["query_en"], r  # auto: Tamil in -> Tamil out
r = ask("What does the learning rate do?", "ml"); assert r["covered"] and "Malayalam" in SEEN[-1]
r = ask("learning rate kya hota hai", "auto"); assert r["covered"] and r["lang"] == "hi", r              # romanised Hindi
r = ask("Who won the 2018 World Cup?", "ta"); assert not r["covered"] and r["answer"] == L.LANGS["ta"]["refuse"], r
assert c.get("/api/revision/%d?lang=ml" % uid).status_code == 200
print("LANG TESTS OK")
