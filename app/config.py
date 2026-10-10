import os
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
SERVERLESS = bool(os.getenv("STUDYPILOT_INLINE_JOBS"))  # dormant testing switch: run jobs inline instead of in a background thread
DATA = Path(os.getenv("DATA_DIR") or ("/tmp/studypilot" if SERVERLESS else ROOT / "data"))
DATA.mkdir(parents=True, exist_ok=True)

# ---- per-user workspaces: every learner gets an isolated DB + uploads + media + eval folder ----
import contextvars
CURRENT_USER = contextvars.ContextVar("studypilot_user", default=0)


def workspace(uid=None):
    uid = CURRENT_USER.get() if uid is None else uid
    w = DATA / "users" / str(int(uid))
    for d in (w, w / "uploads", w / "media", w / "eval"): d.mkdir(parents=True, exist_ok=True)
    return w


def __getattr__(name):  # C.DB_PATH / C.UPLOADS / C.MEDIA / C.EVAL resolve to the current user's workspace
    if name == "DB_PATH": return workspace() / "studypilot.db"
    if name == "UPLOADS": return workspace() / "uploads"
    if name == "MEDIA": return workspace() / "media"
    if name == "EVAL": return workspace() / "eval"
    raise AttributeError(name)

g = os.getenv
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")  # Windows: silence the harmless Hugging Face cache warning

# ---- database: SQLite by default; set DATABASE_URL to a Supabase (Postgres) connection string to use Supabase ----
DATABASE_URL = (g("DATABASE_URL") or "").strip()
USE_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))
DB_POOL_MAX = int(g("DB_POOL_MAX", "10"))

# OpenRouter is the sole online AI provider; old LLM_PROVIDER values are ignored.
PROVIDER = "openrouter" if (g("OPENROUTER_API_KEY") or "").strip() else "offline"
VERIFY_PROVIDER = PROVIDER
MODELS = {"openrouter": g("OPENROUTER_MODEL", "google/gemma-4-31b-it:free").strip()}
KEYS = {"openrouter": (g("OPENROUTER_API_KEY") or "").strip()}
OPENROUTER_BASE = g("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
_OR_ALT = g("OPENROUTER_FALLBACK_MODELS", "inclusionai/ling-3.1-flash,openrouter/free")
OPENROUTER_MODELS = list(dict.fromkeys(m.strip() for m in [MODELS["openrouter"]] + _OR_ALT.split(",") if m.strip()))
OPENROUTER_VISION = g("OPENROUTER_VISION", "0") == "1"
LLM_TIMEOUT = max(5, float(g("LLM_TIMEOUT", "30")))
LLM_ATTEMPT_TIMEOUT = max(3, float(g("LLM_ATTEMPT_TIMEOUT", "15")))
QUIZ_AI_SECONDS = max(5, float(g("QUIZ_AI_SECONDS", "25")))
WHISPER_MODEL = g("WHISPER_MODEL", "base")
FRAME_EVERY = int(g("FRAME_EVERY", "45"))
EMBEDDINGS = g("EMBEDDINGS", "0") == "1"
