"""Checks for the v4 features: spaced repetition, audio overview, teach-back, glossary, Anki export. Offline, plus a mocked-AI run of the grounding guard."""
import os, sys, tempfile, time, json
from pathlib import Path
os.environ["DATA_DIR"] = tempfile.mkdtemp(); os.environ["LLM_PROVIDER"] = "offline"
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["DATABASE_URL"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient
from app.main import app
from app import config as C, srs, retrieval
FX = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
c = TestClient(app); ok = lambda m: print("PASS", m)
sid = c.post("/api/students", json={"name": "Asha"}).json()["id"]; c.cookies.set("sp_user", str(sid))
j = c.post("/api/upload", files=[("files", (n, open(FX / n, "rb"))) for n in ("intro_ml_textbook.pdf", "intro_ml_lecture.vtt", "intro_ml_slides.pptx")]).json()["job"]
while c.get(f"/api/jobs/{j}").json()["status"] == "running": time.sleep(.3)
C.CURRENT_USER.set(sid)
# ---- spaced repetition
b = c.post(f"/api/review/{sid}/build", json={"per_topic": 6}).json(); assert b["added"] >= 6 and b["total"] == b["added"], b
b2 = c.post(f"/api/review/{sid}/build", json={"per_topic": 6}).json(); assert b2["added"] == 0; ok(f"deck built from weak topics ({b['added']} cards), rebuilding adds no duplicates")
d = c.get(f"/api/review/{sid}/due").json(); cards = d["cards"]; assert cards and cards[0]["source"]["label"] and set(cards[0]["preview"]) == {"again", "hard", "good", "easy"}
p = cards[0]["preview"]; assert p["again"] < 0.01 < p["hard"] <= p["good"] < p["easy"], p; ok(f"due queue with source links + interval previews {p}")
mast0 = {m["topic_id"]: m["p_know"] for m in c.get(f"/api/dashboard/{sid}").json()["mastery"]}
c0 = cards[0]; g1 = c.post(f"/api/review/{sid}/grade", json={"id": c0["id"], "grade": "good"}).json(); assert g1["next_due_days"] == 1.0
g2 = c.post(f"/api/review/{sid}/grade", json={"id": c0["id"], "grade": "good"}).json(); assert g2["next_due_days"] == 3.0
g3 = c.post(f"/api/review/{sid}/grade", json={"id": c0["id"], "grade": "easy"}).json(); assert g3["next_due_days"] > 7; ok(f"SM-2 intervals grow with recall: 1d -> 3d -> {g3['next_due_days']}d")
mast1 = {m["topic_id"]: m["p_know"] for m in c.get(f"/api/dashboard/{sid}").json()["mastery"]}; assert mast1[c0["topic_id"]] > mast0[c0["topic_id"]]
other = next((x for x in cards[1:] if x["topic_id"] != c0["topic_id"]), cards[1]); pre = mast1[other["topic_id"]]
ag = c.post(f"/api/review/{sid}/grade", json={"id": other["id"], "grade": "again"}).json(); assert ag["next_due_days"] < 0.01
post = {m["topic_id"]: m["p_know"] for m in c.get(f"/api/dashboard/{sid}").json()["mastery"]}[other["topic_id"]]; assert (post - pre) < (mast1[c0["topic_id"]] - mast0[c0["topic_id"]]) / 3, (post - pre, mast1[c0["topic_id"]] - mast0[c0["topic_id"]])
assert c0["id"] not in [x["id"] for x in c.get(f"/api/review/{sid}/due").json()["cards"]]; ok("graded cards leave the due queue; 'again' returns in minutes; recall raises mastery much more than a lapse")
assert c.get(f"/api/dashboard/{sid}").json()["reviews"]["total"] == b["added"]
tsv = c.get(f"/api/export/{sid}/anki.tsv"); assert tsv.status_code == 200 and tsv.text.count("\n") + 1 == b["added"] and all(len(l.split("\t")) == 3 for l in tsv.text.split("\n")); ok("Anki export: one tab-separated line per card, with source")
# ---- audio overview
mast = c.get(f"/api/dashboard/{sid}").json()["mastery"]; weakest = sorted(mast, key=lambda m: m["p_eff"])[0]["topic_id"]
po = c.post(f"/api/podcast/{sid}", json={}).json(); T = po["turns"]
assert len(T) >= 8 and {t["speaker"] for t in T} == {"Alex", "Sam"} and po["grounding"]["supported_pct"] == 1.0 and any(t["source"] for t in T)
assert all(t["source"]["label"] for t in T if t["source"]); ok(f"two-host audio overview: {len(T)} turns about {po['topics']}, {sum(1 for t in T if t['source'])} factual turns each with a source")
# ---- grounding guard for the AI path (mock OpenRouter that hallucinates one turn)
import httpx
from app import llm
C.KEYS["openrouter"] = "TEST"; C.PROVIDER = "openrouter"; U = [u for u in retrieval.get_index().units if u["topic_id"] == po and False] if False else None
tid = [m["topic_id"] for m in sorted(mast, key=lambda m: m["p_eff"])][0]
units = [u for u in retrieval.get_index().units if u["topic_id"] == tid and len(u["text"].split()) >= 8]; u0 = units[0]
good = [s for s in __import__("app.nlp", fromlist=["x"]).sentences(u0["text"]) if len(s.split()) >= 6][0]
class R:
    status_code = 200; text = ""
    def __init__(s, t): s.t = t
    def json(s): return {"choices": [{"message": {"content": s.t}}]}
def fake(url, headers=None, json=None, timeout=None):
    sysm = json["messages"][0]["content"]
    if "podcasts" in sysm: return R(__import__("json").dumps([{"speaker": "Alex", "text": good, "source_unit_id": u0["id"]},
        {"speaker": "Sam", "text": "Why?", "source_unit_id": None}, {"speaker": "Alex", "text": "Bananas orbit Jupiter and cause every overfitting outage in deep ocean sonar.", "source_unit_id": u0["id"]}]))
    if "fact-checker" in sysm: return R('{"supported": [true, true]}')
    return R("not json")
llm._send = fake
po2 = c.post(f"/api/podcast/{sid}", json={"topics": [tid]}).json()
assert po2["grounding"]["dropped"] >= 1 and not any("Bananas" in t["text"] for t in po2["turns"]); ok(f"AI path: hallucinated turn dropped by the grounding guard ({po2['grounding']})")
C.KEYS["openrouter"] = ""; C.PROVIDER = "offline"
# ---- teach-back
tb = [m for m in mast if m["topic_id"] == tid][0]
units_t = [u for u in retrieval.get_index().units if u["topic_id"] == tid]
full = " ".join(u["text"][:300] for u in units_t[:3])
r1 = c.post(f"/api/teachback/{sid}", json={"topic_id": tid, "text": full}).json()
r2 = c.post(f"/api/teachback/{sid}", json={"topic_id": tid, "text": "Honestly I think this is about cooking pasta and the weather on Mars being quite cold in winter."}).json()
assert r1["score"] > r2["score"] and r2["flagged"] and r2["accuracy"] < r1["accuracy"], (r1["score"], r2["score"]); ok(f"teach-back: faithful explanation {r1['score']} > off-topic one {r2['score']}; unsupported sentences flagged")
assert (r2["missing"] or r2["covered"]) is not None and r2["feedback"]; short = c.post(f"/api/teachback/{sid}", json={"topic_id": tid, "text": "idk"}); assert short.status_code == 400
assert len(c.get(f"/api/teachback/{sid}/history").json()) == 2; ok("teach-back history saved; too-short answers rejected")
# ---- glossary
gl = c.get("/api/glossary").json(); assert len(gl) >= 5 and all(g["definition"] and g["source"]["label"] for g in gl)
from app import grounding
allu = retrieval.get_index().units; assert all(grounding.support(g["definition"], allu) >= 0.9 for g in gl); ok(f"glossary: {len(gl)} terms, each definition is a sentence from your material with its source")
print("ALL V4 CHECKS PASSED")
