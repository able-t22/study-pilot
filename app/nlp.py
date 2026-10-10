import re
STOP = set("""a an the and or but if then else of to in on at by for with from as is are was were be been being this that these those it its
we you they he she i not no do does did done can could should would may might will shall than so such into over under between about
also more most other some any each both which who whom whose what when where why how there here their our your his her them us me my
very just only own same too one two use used using given via per et al e g i e etc title notes speaker figure ocr""".split())
HI_STOP = set("है और का की के में से को यह पर एक हैं था थी थे कि जो तो भी या इस उस हम आप वह".split())
TOK = re.compile(r"[\w\u0900-\u097F\u0B80-\u0BFF\u0D00-\u0D7F]+", re.U)


def stem(w):
    if w.endswith(("ss", "us", "is")): return w
    for suf in ("ization", "ations", "ation", "ments", "ment", "ingly", "ings", "ing", "edly", "ies", "ed", "es", "ly", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[:-len(suf)] + ("y" if suf == "ies" else "")
    return w


def tokens(text):
    out = []
    for w in TOK.findall((text or "").lower()):
        if w in STOP or w in HI_STOP or w.isdigit() and len(w) > 4 or len(w) < 2:
            continue
        out.append(stem(w))
    return out


def analyze(text):
    t = tokens(text)
    return t + [a + "_" + b for a, b in zip(t, t[1:])]


def sentences(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    return [s.strip() for s in re.split(r"(?<=[\.\?\!।])\s+(?=[A-Z0-9\u0900-\u097F\[\(])", text) if len(s.strip()) > 2]


def chunk_text(text, max_words=170, min_words=25):
    text = (text or "").replace("\r", "")
    paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", text)]
    if len(paras) <= 1:  # single block with hard line breaks
        paras = [re.sub(r"\s+", " ", text).strip()]
    sents = [s for p in paras if p for s in sentences(p)]
    chunks, cur = [], []
    for s in sents:
        cur.append(s)
        if sum(len(x.split()) for x in cur) >= max_words:
            chunks.append(" ".join(cur)); cur = []
    if cur:
        if chunks and sum(len(x.split()) for x in cur) < min_words:
            chunks[-1] += " " + " ".join(cur)
        else:
            chunks.append(" ".join(cur))
    return [c for c in chunks if len(c.split()) >= 5]


def fmt_time(t):
    t = int(t); h, m, s = t // 3600, t % 3600 // 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
