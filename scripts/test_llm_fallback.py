"""OpenRouter-only contract tests; no credentials or network required."""
import os, sys, tempfile, json
from pathlib import Path
os.environ.update(DATA_DIR=tempfile.mkdtemp(), OPENROUTER_API_KEY="TEST", OPENROUTER_MODEL="test/primary", OPENROUTER_FALLBACK_MODELS="test/backup")
os.environ["DATABASE_URL"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import llm, config as C
import httpx

class Reply:
    def __init__(self, code=200, body=None, headers=None):
        self.status_code = code
        self.body = body if body is not None else {"choices": [{"message": {"content": "answer"}}], "model": "actual/model"}
        self.text = json.dumps(self.body)
        self.headers = headers or {}
    def json(self): return self.body

calls, plan = [], []
def post(url, headers=None, json=None, timeout=None):
    assert url == C.OPENROUTER_BASE + "/chat/completions"
    assert headers["Authorization"] == "Bearer TEST"
    assert 0 < timeout <= C.LLM_TIMEOUT
    calls.append(json.copy())
    result = plan.pop(0)
    if isinstance(result, Exception): raise result
    return result
llm._send = post

def run(*replies, **kw):
    calls.clear(); plan[:] = replies; llm._cool.clear()
    return llm.chat("system", "question", **kw)

assert C.PROVIDER == "openrouter" and llm.chain() == ["openrouter"]
assert set(C.KEYS) == {"openrouter"}
assert run(Reply()) == "answer" and len(calls) == 1
assert llm.STATE["last_model"] == "actual/model"
assert run(Reply(429, {"error": "limited"}), Reply()) == "answer"
assert [c["model"] for c in calls] == ["test/primary", "test/backup"]
# A limited primary is skipped on the next call.
plan[:] = [Reply()]; calls.clear(); llm.chat("sys", "user")
assert calls[0]["model"] == "test/backup"
for code in (401, 403, 400):
    try: run(Reply(code, {"error": "invalid"}), Reply())
    except RuntimeError: assert len(calls) == 1
    else: raise AssertionError("invalid request should fail")
for code in (404, 503):
    assert run(Reply(code, {"error": "unavailable"}), Reply()) == "answer"
assert run(Reply(body={"error": {"code": "429", "message": "limited"}}), Reply()) == "answer"
assert run(Reply(body={"choices": [{"message": {"content": ""}}]}), Reply()) == "answer"
assert run(httpx.ConnectError("down"), Reply()) == "answer"
assert run(Reply(400, {"error": "response_format unsupported"}), Reply(), json_mode=True) == "answer"
assert "response_format" in calls[0] and "response_format" not in calls[1]
try: run(Reply(429), Reply(429))
except llm.ProviderUnavailable: pass
else: raise AssertionError("all models should fail")
before = len(calls)
try: llm.chat("sys", "user")
except llm.ProviderUnavailable: assert len(calls) == before
else: raise AssertionError("cooldown should avoid new calls")
llm._cool.clear(); calls.clear()
with llm.request_budget(0):
    assert not llm.has_budget()
    try: llm.chat("sys", "user")
    except llm.ProviderUnavailable: pass
    else: raise AssertionError("expired budget should fail immediately")
assert not calls and llm.has_budget()
assert llm.parse_json('prose {"questions": []} end') == {"questions": []}
assert llm.parse_json('not json') is None
print("OPENROUTER TESTS OK")
