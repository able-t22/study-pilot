"""CLI evaluation: python scripts/run_eval.py   (uses whatever is currently ingested; loads the sample course if empty)"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import db, ingest, kb, evals, simulate, config as C

if not db.q1("SELECT COUNT(*) n FROM units")["n"]:
    print("No material found - ingesting the sample course...")
    for f in ("intro_ml_textbook.pdf", "intro_ml_slides.pptx", "intro_ml_lecture.vtt"):
        ingest.ingest_file(C.ROOT / "tests" / "fixtures" / f)
    kb.build()
print("== RAG evaluation =="); r = evals.run(20, lambda m, p: print(f"  {m}")); print(json.dumps(r["metrics"], indent=1))
for c in r["caveats"]: print("  caveat:", c)
print("== Simulated students =="); s = simulate.run(30, progress=lambda m, p: print(f"  {m}"))
print(json.dumps({k: s[k] for k in ("comparison",)}, indent=1)); print("adaptive:", {k: s["adaptive"][k] for k in ("mean_gain", "repetition_rate")}, "random:", {k: s["random"][k] for k in ("mean_gain", "repetition_rate")})
print("Results saved in", C.EVAL)
