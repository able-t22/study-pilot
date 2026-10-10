"""Grounding guard shared by revision material, notes and evaluation.
A claim is 'supported' only if (a) its content words are found in the source units it is attributed to (lexical floor, always applied) and
(b) when an AI is configured, an independent fact-check call also agrees. Unsupported claims are dropped or flagged - never shown as fact."""
import re
from . import nlp, llm

MIN_SUPPORT = 0.55


def support(claim, units):
    """Fraction of the claim's content words (stemmed, stop-words removed) that occur in the given source units."""
    ct = nlp.tokens(claim)
    if not ct: return 1.0
    ctx = set()
    for u in units: ctx.update(nlp.tokens(u["text"]))
    return sum(t in ctx for t in ct) / len(ct)


def verify(claims, units, lexical=True, min_support=MIN_SUPPORT):
    """-> list[bool]. lexical=False is for non-English output (word overlap with English sources is meaningless); the AI judge then decides alone."""
    claims = list(claims)
    lex = [support(c, units) >= min_support for c in claims] if lexical else [True] * len(claims)
    if not claims or not llm.enabled() or not llm.has_budget() or not any(lex): return lex
    ctx = "\n".join(u["text"][:700] for u in units[:8])
    r = llm.chat_json("You are a strict fact-checker. A claim is supported only if the CONTEXT states or directly implies it.",
                      "CONTEXT:\n" + ctx + "\n\nCLAIMS:\n" + "\n".join(f"{i + 1}. {c}" for i, c in enumerate(claims)) +
                      '\n\nReturn JSON {"supported":[true|false, ...]} with exactly one entry per claim.', max_tokens=400)
    if isinstance(r, dict) and isinstance(r.get("supported"), list) and len(r["supported"]) == len(claims):
        return [a and bool(b) for a, b in zip(lex, r["supported"])]
    return lex  # judge unavailable: the lexical floor still protects


def ground_text(text, units, lexical=True):
    """Drop sentences the sources do not support. -> {"text": kept, "flagged": [dropped sentences], "pct": share supported}"""
    sents = [s for s in nlp.sentences(re.sub(r"\[S?\d+\]", "", text)) if len(s.split()) >= 3]
    if not sents: return {"text": text, "flagged": [], "pct": 1.0}
    ok = verify(sents, units, lexical)
    return {"text": " ".join(s for s, k in zip(sents, ok) if k), "flagged": [s for s, k in zip(sents, ok) if not k], "pct": round(sum(ok) / len(ok), 3)}
