"""Multilingual layer: the ANSWER language is independent of the QUESTION language and of the (usually English) source material."""
import re
from . import llm

LANGS = {
    "en": {"name": "English", "native": "English", "speech": "en-IN", "prompt": "English",
           "refuse": "I couldn't find this in your uploaded course material, so I won't present an answer as source-backed."},
    "hi": {"name": "Hindi", "native": "हिन्दी", "speech": "hi-IN", "prompt": "Hindi (Devanagari script)",
           "refuse": "यह जानकारी मुझे आपकी अपलोड की गई सामग्री में नहीं मिली, इसलिए मैं इसे स्रोत-आधारित उत्तर के रूप में नहीं दूँगा।"},
    "ta": {"name": "Tamil", "native": "தமிழ்", "speech": "ta-IN", "prompt": "Tamil (Tamil script)",
           "refuse": "நீங்கள் பதிவேற்றிய பாடப்பொருளில் இது எனக்குக் கிடைக்கவில்லை, எனவே இதை மூலம்-சார்ந்த பதிலாக வழங்க மாட்டேன்."},
    "ml": {"name": "Malayalam", "native": "മലയാളം", "speech": "ml-IN", "prompt": "Malayalam (Malayalam script)",
           "refuse": "നിങ്ങൾ അപ്‌ലോഡ് ചെയ്ത പഠനസാമഗ്രിയിൽ ഇത് കണ്ടെത്താനായില്ല, അതിനാൽ ഇത് ഉറവിടം അടിസ്ഥാനമാക്കിയ ഉത്തരമായി നൽകില്ല."},
}
SCRIPTS = {"hi": re.compile(r"[\u0900-\u097F]"), "ta": re.compile(r"[\u0B80-\u0BFF]"), "ml": re.compile(r"[\u0D00-\u0D7F]")}


def valid(code): return code if code in LANGS else "en"


def prompt_name(code): return LANGS[valid(code)]["prompt"]


def detect_script(text):
    """Language from script alone ('en' for Latin text - romanised Hindi etc. is handled by the LLM translate step)."""
    best, n = "en", 0
    for code, rx in SCRIPTS.items():
        c = len(rx.findall(text or ""))
        if c > n: best, n = code, c
    return best


def to_english(question):
    """Return (english_query, detected_lang). Needed because course material is searched lexically in its own language.
    Handles native script and romanised input ('learning rate kya hota hai'). Offline: returns the text unchanged."""
    if not llm.enabled(): return question, detect_script(question)
    r = llm.chat_json("You translate student questions for a search engine over English course material. Keep technical terms. "
                      "The input may be English, Hindi, Tamil, Malayalam, or romanised/mixed (e.g. Hinglish, Manglish, Tanglish).",
                      f'Question: {question}\n\nReturn JSON {{"english": "the question in clear English", "lang": "en|hi|ta|ml (language the student wrote in)"}}', max_tokens=200)
    if isinstance(r, dict) and r.get("english"):
        return str(r["english"]), valid(r.get("lang") or detect_script(question))
    return question, detect_script(question)


def resolve(choice, question_lang):
    """'auto' = answer in the language the student asked in."""
    return valid(question_lang) if choice in (None, "", "auto") else valid(choice)
