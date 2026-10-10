"""OpenRouter only: bounded model failover, reusable connections, and visible diagnostics."""
import base64, contextvars, json, re, threading, time
from contextlib import contextmanager
import httpx
from . import config as C

class ProviderUnavailable(RuntimeError):
    def __init__(self, msg, retry_after=None, code=None):
        super().__init__(msg)
        self.retry_after, self.code = retry_after, code

OR_UNAVAILABLE = (404, 408, 429, 500, 502, 503, 504, 529)
UNAVAILABLE = OR_UNAVAILABLE
_cool = {}
_deadline = contextvars.ContextVar("llm_deadline", default=float("inf"))
_client = httpx.Client(follow_redirects=True, limits=httpx.Limits(max_connections=10, max_keepalive_connections=5))
_lock = threading.RLock()
LAST_ERROR = {"msg": ""}
STATE = {"last_provider": None, "last_model": None, "last_failover": None,
         "status": "untested", "last_success": None, "latency_ms": None, "error_code": None}

@contextmanager
def request_budget(seconds):
    token = _deadline.set(min(_deadline.get(), time.monotonic() + seconds))
    try: yield
    finally: _deadline.reset(token)

def has_budget(): return time.monotonic() < _deadline.get()
def enabled(provider=None): return (provider or C.PROVIDER) == "openrouter" and bool(C.KEYS.get("openrouter"))
def chain(p=None): return ["openrouter"] if enabled(p) else []
def vision_enabled(): return enabled() and C.OPENROUTER_VISION
def _vision_ok(p): return p == "openrouter" and C.OPENROUTER_VISION
def _send(url, **kw): return _client.post(url, **kw)

def _retry_delay(text):
    m = re.search(r'retry(?:Delay"?:\s*"?| in )(\d+(?:\.\d+)?)s', text, re.I)
    return float(m.group(1)) if m else None

def _retry_after(r):
    try: return float(r.headers.get("retry-after"))
    except (ValueError, TypeError, AttributeError): return _retry_delay(r.text or "")

def _message(body, status):
    error = body.get("error", {}) if isinstance(body, dict) else {}
    message = str(error.get("message", error) if isinstance(error, dict) else error)[:200]
    if status == 401: return "OpenRouter rejected the API key. Check OPENROUTER_API_KEY and restart the server."
    if status == 402: return "OpenRouter reports insufficient credits or an account spending limit. Check your account balance and limits."
    if status == 403: return "OpenRouter access was denied. Check account permissions and model/data-policy settings."
    if status == 429: return "OpenRouter rate limit reached. " + message
    if status == 404: return "OpenRouter model or compatible endpoint unavailable. " + message
    return f"OpenRouter error {status}: {message}"

def _post(url, headers, payload, timeout=None, provider=None, failfast=True, unavailable=OR_UNAVAILABLE):
    try:
        r = _send(url, headers=headers, json=payload, timeout=timeout or C.LLM_ATTEMPT_TIMEOUT)
    except (httpx.TimeoutException, httpx.TransportError) as e:
        label = "timeout" if isinstance(e, httpx.TimeoutException) else "connection"
        raise ProviderUnavailable(f"OpenRouter {label} failed ({type(e).__name__}). Check network/proxy access to openrouter.ai.", code=label) from e
    try: body = r.json()
    except ValueError: raise ProviderUnavailable("OpenRouter returned an unreadable response", code="response")
    code = r.status_code
    if isinstance(body, dict) and body.get("error"):
        try: code = int(body["error"].get("code", code if code >= 400 else 503))
        except (ValueError, TypeError, AttributeError): code = code if code >= 400 else 503
    if code >= 400:
        msg = _message(body, code)
        if code in unavailable or code in (401, 402, 403): raise ProviderUnavailable(msg, _retry_after(r), code)
        raise RuntimeError(msg)
    return body

def _openrouter_once(model, system, user, images, json_mode, max_tokens, temperature, web, meta, deadline):
    content = [{"type": "text", "text": user}] + [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(b).decode()}} for b in images]
    payload = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": content if images else user}],
               "reasoning": {"enabled": False}, "provider": {"allow_fallbacks": True}}
    if json_mode and model != "inclusionai/ling-3.1-flash": payload["response_format"] = {"type": "json_object"}
    if web: payload["plugins"] = [{"id": "web", "max_results": 3}]
    headers = {"Authorization": "Bearer " + C.KEYS["openrouter"], "X-Title": "StudyPilot", "Content-Type": "application/json"}
    for attempt in range(2):
        remaining = deadline - time.monotonic()
        if remaining <= 0: raise ProviderUnavailable("OpenRouter request budget exhausted", code="timeout")
        try:
            body = _post(C.OPENROUTER_BASE + "/chat/completions", headers, payload, timeout=min(C.LLM_ATTEMPT_TIMEOUT, remaining))
            break
        except RuntimeError as e:
            if isinstance(e, ProviderUnavailable): raise
            if attempt or not re.search(r"response_format|json mode|reasoning|unsupported.*parameter", str(e), re.I): raise
            payload.pop("response_format", None); payload.pop("reasoning", None)
    try:
        message = body["choices"][0]["message"]
        text = message.get("content")
        if isinstance(text, list): text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
    except (KeyError, TypeError, IndexError, AttributeError): raise ProviderUnavailable("OpenRouter returned no usable answer", code="response")
    if not isinstance(text, str) or not text.strip(): raise ProviderUnavailable("OpenRouter produced no final answer; try another model", code="empty")
    if body["choices"][0].get("finish_reason") == "length" and json_mode:
        raise ProviderUnavailable("OpenRouter truncated the structured answer", code="truncated")
    if meta is not None:
        meta["provider"] = "openrouter"; meta["model"] = body.get("model") or model
        meta["sources"] = [{"title": a["url_citation"].get("title", ""), "url": a["url_citation"]["url"]} for a in message.get("annotations", []) if isinstance(a, dict) and a.get("url_citation", {}).get("url")][:5]
    with _lock: STATE["last_model"] = body.get("model") or model
    return text.strip()

def chat(system, user, images=None, json_mode=False, max_tokens=2500, provider=None, temperature=.2, web=False, meta=None):
    if not enabled(provider): raise RuntimeError("OpenRouter is not configured. Add OPENROUTER_API_KEY to .env and restart.")
    images = images or []
    if images and not vision_enabled(): raise RuntimeError("The configured OpenRouter models do not have vision enabled")
    started = time.monotonic()
    deadline = min(_deadline.get(), started + C.LLM_TIMEOUT)
    if deadline <= started: raise ProviderUnavailable("OpenRouter request budget exhausted", code="timeout")
    with _lock: models = [m for m in C.OPENROUTER_MODELS if _cool.get(m, 0) <= time.time()]
    if not models: raise ProviderUnavailable(LAST_ERROR["msg"] or "OpenRouter models are temporarily rate limited. Retry shortly.", code=429)
    error = None
    for i, model in enumerate(models):
        if not has_budget() or time.monotonic() >= deadline: break
        try:
            out = _openrouter_once(model, system, user, images, json_mode, max_tokens, temperature, web, meta, deadline)
            with _lock:
                STATE.update(last_provider="openrouter", status="connected", last_success=time.time(), latency_ms=round((time.monotonic()-started)*1000), error_code=None)
                LAST_ERROR["msg"] = ""
            return out
        except (ProviderUnavailable, RuntimeError) as e:
            error = e; code = getattr(e, "code", None)
            with _lock:
                LAST_ERROR["msg"] = str(e)[:300]; STATE.update(status="error", error_code=code)
            if code in (401, 402, 403) or not isinstance(e, ProviderUnavailable): break
            wait = min(max(getattr(e, "retry_after", None) or (20 if code == 429 else 3), 1), 120)
            with _lock: _cool[model] = time.time() + wait
            if i + 1 < len(models): STATE["last_failover"] = time.time()
    raise error or ProviderUnavailable("OpenRouter request timed out", code="timeout")

def parse_json(text):
    if not isinstance(text, str) or not text.strip(): return None
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    fence = chr(96) * 3
    if text.startswith(fence): text = re.sub("^" + fence + r"(?:json)?\s*", "", text)
    if text.endswith(fence): text = text[:-3].rstrip()
    # Repair common TeX commands emitted with a single JSON backslash.
    text = re.sub(r'(?<!\\)\\(?=(?:frac|beta|bar|begin|theta|text|times|nabla|nu|rho|right|sqrt|sum|int|alpha|pi|sigma)\b)', r'\\\\', text)
    try: return json.loads(text)
    except ValueError: pass
    decoder = json.JSONDecoder(strict=False)
    for m in re.finditer(r"[\[{]", text):
        try: return decoder.raw_decode(text[m.start():])[0]
        except ValueError: pass
    repaired = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', text)
    try: return json.loads(repaired, strict=False)
    except ValueError: return None

def chat_json(system, user, **kw):
    try:
        text = chat(system, user + "\nReturn one JSON object only. Wrap lists in a named property. Escape all backslashes in JSON strings.", json_mode=True, **kw)
        result = parse_json(text)
        if result is None:
            LAST_ERROR["msg"] = "OpenRouter returned invalid JSON. Try a smaller request or another model."
            STATE.update(status="error", error_code="json")
        return result
    except Exception as e:
        LAST_ERROR["msg"] = str(e)[:300]
        return None

def diagnostics(probe=False):
    data = {"configured": enabled(), "model": C.MODELS["openrouter"], "models": C.OPENROUTER_MODELS,
            "status": STATE["status"] if enabled() else "not_configured", "last_error": LAST_ERROR["msg"],
            "last_model": STATE["last_model"], "last_success": STATE["last_success"], "latency_ms": STATE["latency_ms"], "error_code": STATE["error_code"]}
    if probe and enabled():
        meta = {}
        try:
            with request_budget(20): chat("You test connectivity.", "Reply with OK only.", max_tokens=64, meta=meta)
            data.update(status="connected", last_model=meta.get("model"), latency_ms=STATE["latency_ms"], last_error="")
        except Exception as e: data.update(status="error", last_error=str(e), error_code=getattr(e,"code",None))
    return data
