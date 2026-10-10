"""Wiring test for the DeepEval adapter with a STUB judge (no network): proves the real DeepEval metrics run on StudyPilot's real pipeline output."""
import enum, os, sys, tempfile, time, typing
from pathlib import Path
os.environ["DATA_DIR"] = tempfile.mkdtemp(); os.environ["LLM_PROVIDER"] = "offline"; os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient
from app.main import app
from app import config as C, fw_eval
from deepeval.models import DeepEvalBaseLLM
from pydantic import BaseModel
FX = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

def build(tp):
    """Generic schema-valid instance: lists of str -> one claim, lists of models -> one 'yes' verdict, str -> 'yes', numbers -> 1."""
    if isinstance(tp, type) and issubclass(tp, BaseModel):
        return tp(**{n: build(f.annotation) for n, f in tp.model_fields.items()})
    if isinstance(tp, type) and issubclass(tp, enum.Enum): return list(tp)[0]   # first member = YES
    o, a = typing.get_origin(tp), typing.get_args(tp)
    if o is typing.Literal: return a[0]
    if o in (list, typing.List): return [build(a[0])]
    if o is typing.Union: return build([x for x in a if x is not type(None)][0])
    if tp is str: return "yes"
    if tp is bool: return True
    if tp in (int, float): return 1
    return None

class Stub(DeepEvalBaseLLM):
    def __init__(self): super().__init__(model="stub")
    def load_model(self): return self
    def get_model_name(self): return "stub-judge"
    def generate(self, prompt, schema=None, **kw): return build(schema) if schema else "yes"
    async def a_generate(self, prompt, schema=None, **kw): return self.generate(prompt, schema)

c = TestClient(app); sid = c.post("/api/students", json={"name": "A"}).json()["id"]; c.cookies.set("sp_user", str(sid))
j = c.post("/api/upload", files=[("files", (n, open(FX / n, "rb"))) for n in ("intro_ml_textbook.pdf", "intro_ml_lecture.vtt", "intro_ml_slides.pptx")]).json()["job"]
while c.get(f"/api/jobs/{j}").json()["status"] == "running": time.sleep(.3)
C.CURRENT_USER.set(sid)
res = fw_eval.run(4, judge=Stub())
print({k: v for r in res["rows"][:1] for k, v in r.items() if k.endswith("_error")}); print(res["framework"], res["judge"], res["n_answered"], "answered | metrics:", res["metrics"], "| errors:", res["metric_errors"])
assert res["n_answered"] >= 3 and res["metric_errors"] == 0 and all(v is not None for v in res["metrics"].values()), res
print("PASS DeepEval Faithfulness / AnswerRelevancy / ContextualPrecision / ContextualRecall execute on real pipeline output (stub judge)")
# the real judge class builds and validates structured output through StudyPilot's LLM layer
from app import llm
class P(BaseModel): verdict: str
j = fw_eval.make_judge(); llm.chat = lambda *a, **k: '```json\n{"verdict": "yes"}\n```'
assert j.generate("x", P).verdict == "yes" and j.get_model_name().startswith("StudyPilot"); print("PASS StudyPilotJudge parses structured output via the OpenRouter layer")
