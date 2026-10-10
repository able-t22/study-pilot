"""Readable concept checks with exact source support, available without AI."""
import re
from . import nlp

def facts(units):
    out=[]; seen=set()
    for u in units:
        text=re.sub(r"^(Speaker notes: )", "", u["text"])
        for sentence in nlp.sentences(text):
            sentence=sentence.strip().strip("•- ")
            if not 6 <= len(sentence.split()) <= 65 or sentence in seen: continue
            m=re.match(r"^([A-Za-z][A-Za-z0-9 ()/,\-]{2,85}?)\s+(is|are|refers to|means|measures|describes|controls|provides|uses|reduces|increases|updates|calculates|represents|enables|contains|consists of|helps)\s+(.+)", sentence, re.I)
            if not m: continue
            subject,verb,rest=m.groups()
            if len(subject.split())>12 or subject.lower() in ("it","this","that","these","there","they"): continue
            seen.add(sentence)
            out.append({"subject":subject,"verb":verb.lower(),"predicate":verb+" "+rest,"sentence":sentence,"unit":u})
    return out

def questions(units,n,rng,types=("mcq","short")):
    fs=facts(units);rng.shuffle(fs);out=[]
    for f in fs:
        subject=f["subject"]; verb=f["verb"]; pred=f["predicate"]; unit=f["unit"]
        opts=None;typ="short"
        alternatives=list(dict.fromkeys(x["predicate"] for x in fs if x["subject"].lower()!=subject.lower() and x["predicate"]!=pred and x["verb"]==verb))
        if "mcq" in types and len(alternatives)>=3:
            typ="mcq";opts=rng.sample(alternatives,3)+[pred];rng.shuffle(opts)
            stem=f"Which statement correctly describes {subject}?"
            answer=pred
        elif "short" in types or "mcq" in types:
            stem=f"Explain the meaning of {subject}." if verb in ("is","are","means","refers to") else f"What does {subject} do?"
            answer=f["sentence"]
        else: continue
        out.append(dict(qtype=typ,stem=stem,options=opts,answer=answer,explanation=f["sentence"],
                        unit_id=unit["id"],difficulty="easy",extra={"local_concept":True,"evidence_quote":f["sentence"],"keywords":nlp.tokens(pred)}))
        if len(out)>=n:break
    return out

def numerical_questions(units,n,rng,types):
    """Apply explicitly present square-root / Pythagorean / mean-square definitions."""
    import math
    if not ({"numerical", "mcq"} & set(types)): return []
    out=[]
    for u in units:
        text=u["text"].lower()
        kind="pythagoras" if "pythagor" in text or re.search(r"sqrt\s*\{?a\^2\s*\+\s*b\^2",text) else "sqrt" if "square root" in text or "\\sqrt" in text else "mse" if "mean squared error" in text and ("average" in text or "mean" in text) else None
        if not kind:continue
        for i in range(min(n,8)):
            if kind=="pythagoras":
                a,b=rng.choice([(3,4),(5,12),(8,15),(7,24),(9,12),(6,8),(12,16),(15,20)])
                value=math.hypot(a,b);stem=f"A right triangle has perpendicular sides {a} and {b} units. Use the Pythagorean formula to calculate its hypotenuse."
                calc=f"sqrt({a}**2+{b}**2)";explanation=f"Square both perpendicular sides, add them and take the square root: \\(c=\\sqrt{{{a}^2+{b}^2}}={value:g}\\)."
            elif kind=="sqrt":
                a=i+2;value=a;stem=f"Find the positive value of \\(x=\\sqrt{{{a*a}}}\\), and use the square-root definition to check your result."
                calc=f"sqrt({a*a})";explanation=f"The positive square root is {a}, because \\({a}\\times {a}={a*a}\\)."
            else:
                a,b=i+1,i+3;value=(a*a+b*b)/2
                stem=f"Two prediction errors are {a} and {b}. Calculate their mean squared error."
                calc=f"({a}**2+{b}**2)/2";explanation=f"Square each error, then average: \\(\\mathrm{{MSE}}=\\frac{{{a}^2+{b}^2}}{{2}}={value:g}\\)."
            ans=f"{value:g}";opts=None;typ="numerical" if "numerical" in types else "mcq" if "mcq" in types else "short"
            if typ=="mcq":
                opts=[ans,f"{value+1:g}",f"{value+2:g}",f"{max(0,value-1):g}"];rng.shuffle(opts)
            out.append(dict(qtype=typ,stem=stem,options=opts,answer=ans,explanation=explanation,unit_id=u["id"],difficulty="medium",
                            extra={"local_concept":True,"local_calculation":True,"calc":calc,"tolerance":.01}))
            if len(out)>=n:return out
    return out
