"""Learner accounts. Each learner owns a private workspace (own sources, topics, questions, mastery, notes).
SQLite mode: accounts.json + one DB file per learner.  Supabase/Postgres mode: studypilot.learners table + one schema per learner."""
import json, shutil, threading, time
from . import config as C, db

_lock = threading.Lock()
FILE = C.DATA / "accounts.json"
SEQ = C.DATA / "accounts.seq"   # last id ever issued, so ids are never reused after a delete
_registry_ready = False


def _pg():
    global _registry_ready
    if not _registry_ready: db.ensure_registry(); _registry_ready = True


def _load():
    try: return json.loads(FILE.read_text())
    except Exception: return []


def list_users():
    if C.USE_POSTGRES:
        _pg(); return db.admin_q("SELECT id, name, level, goal, exam_date, created FROM studypilot.learners ORDER BY id")
    return _load()


def get(uid):
    if not uid: return None
    if C.USE_POSTGRES:
        _pg(); r = db.admin_q("SELECT id, name, level, goal, exam_date, created FROM studypilot.learners WHERE id=?", (uid,))
        return r[0] if r else None
    return next((u for u in _load() if u["id"] == uid), None)


def create(name, level="beginner", goal="", exam_date=""):
    name = name.strip()[:60]
    if C.USE_POSTGRES:
        _pg()
        return db.admin_ex("INSERT INTO studypilot.learners(name,level,goal,exam_date,created) VALUES(?,?,?,?,?) RETURNING id",
                           (name, level, goal, exam_date, time.time()))["id"]
    with _lock:
        us = _load()
        try: last = int(SEQ.read_text())
        except Exception: last = 0
        uid = max([u["id"] for u in us] + [last]) + 1
        us.append({"id": uid, "name": name, "level": level, "goal": goal, "exam_date": exam_date, "created": time.time()})
        FILE.write_text(json.dumps(us, indent=1)); SEQ.write_text(str(uid))
    return uid


def delete(uid):
    if C.USE_POSTGRES:
        _pg(); db.admin_ex("DELETE FROM studypilot.learners WHERE id=?", (uid,)); db.drop_learner_schema(uid)
    else:
        with _lock:
            FILE.write_text(json.dumps([u for u in _load() if u["id"] != uid], indent=1))
    db.forget(uid)
    shutil.rmtree(C.DATA / "users" / str(uid), ignore_errors=True)
