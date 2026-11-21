"""Voice for MedBook: speech -> text (faster-whisper) and text -> speech (Meta MMS-TTS, Urdu script).

Both parts are optional and load lazily on first use, so the text chatbot runs without them.

    pip install faster-whisper "av<16"          # speech -> text
    pip install torch transformers              # text -> speech (already installed for XLM-R)

Environment
    MEDBOOK_WHISPER        Whisper size: large-v3-turbo (default, best on Urdu), small (weak laptops), medium, base, tiny
    MEDBOOK_WHISPER_LANG   "ur" (default). Empty lets Whisper detect, which often gives Hindi script.
    MEDBOOK_WHISPER_PROMPT "1" (default) gives Whisper a short clinic vocabulary prompt, "0" turns it off
    MEDBOOK_TTS            "1" (default) spoken replies on, "0" off
    MEDBOOK_VOICE_PRELOAD  "1" loads both models at startup instead of on the first request

Spoken Urdu comes out of Whisper in Urdu script, which the NLU reads, and the dialogue manager then answers in
Urdu script, which MMS-TTS can speak. Roman Urdu replies (to typed Roman messages) are not spoken.
"""
import io
import os
import re
import threading
import time
from functools import lru_cache

WHISPER_MODEL = os.environ.get("MEDBOOK_WHISPER", "large-v3-turbo")   # see DEMO.md section 3 for the comparison
WHISPER_LANG = os.environ.get("MEDBOOK_WHISPER_LANG", "ur") or None
USE_PROMPT = os.environ.get("MEDBOOK_WHISPER_PROMPT", "1") != "0"
TTS_ON = os.environ.get("MEDBOOK_TTS", "1") != "0"
TTS_MODEL = "facebook/mms-tts-urd-script_arabic"

_lock = threading.Lock()
_whisper = {}
_tts = None

URDU_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
ARABIC_RE = re.compile(r"[؀-ۿ]")


def asr_available():
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def tts_available():
    if not TTS_ON:
        return False
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True
    except ImportError:
        return False


# ============================================================================ speech -> text

# Words the clinic hears a lot. Whisper uses the prompt as "previous text", which nudges spelling
# (ڈاکٹر not داکتر, اپائنٹمنٹ not اپائیتمت) without forcing any of it.
PROMPT = ("السلام علیکم، مجھے ڈاکٹر کی اپائنٹمنٹ چاہیے۔ کل، پرسوں، پیر، منگل، صبح، شام۔ بکنگ نمبر ایم بی۔ "
          "بخار، کھانسی، دل، جلد، بچوں کے ڈاکٹر، ای این ٹی، گائناکالوجسٹ۔ منسوخ، تبدیل، جی ہاں۔")


_vocab = ""
_doctor_names = []


def set_vocabulary(doctor_names):
    """Tell the voice layer the clinic's doctor names (Urdu script). They go into the Whisper prompt and are
    used to snap a misheard name back to the real one ("ڈاکٹر شازی کون" -> "ڈاکٹر شازیہ کنول")."""
    global _vocab, _doctor_names
    _doctor_names = [n.replace("ڈاکٹر", "").strip() for n in doctor_names if n]
    _vocab = " ڈاکٹرز: " + "، ".join(_doctor_names) + "۔"


DOCTOR_WORD_RE = re.compile(r"(ڈاکٹر|ڈاکتر|داکٹر|داکتر|ڈکٹر|dr\.?|doctor)[\s،,]+((?:[؀-ۿ]+[\s،,]*){1,3})", re.IGNORECASE)


def snap_doctor_names(text, names=None):
    """After the word "doctor", compare the next one to three words with every doctor's name (letters only)
    and replace them when one name is clearly closest. A closed list of 16 names makes this safe; ordinary words
    after "ڈاکٹر" ("ڈاکٹر سے", "ڈاکٹر کو") are left alone because they are far from every name."""
    import difflib
    names = names if names is not None else _doctor_names
    if not names:
        return text
    squash = lambda s: re.sub(r"[\s،,]", "", s)  # noqa: E731

    def fix(m):
        words = re.findall(r"[؀-ۿ]+", m.group(2))
        best = (0.0, None, 0)
        for k in range(min(3, len(words)), 0, -1):
            cand = squash("".join(words[:k]))
            for n in names:
                r = difflib.SequenceMatcher(None, cand, squash(n)).ratio()
                if r > best[0] + 1e-9:
                    best = (r, n, k)
        r, n, k = best
        if n is None or r < 0.7:
            return m.group(0)
        rest = words[k:]
        return "ڈاکٹر " + n + (" " + " ".join(rest) if rest else "") + (" " if m.group(2)[-1:].isspace() else "")
    return DOCTOR_WORD_RE.sub(fix, text)


def get_whisper(size=None):
    size = size or WHISPER_MODEL
    with _lock:
        if size not in _whisper:
            from faster_whisper import WhisperModel
            _whisper[size] = WhisperModel(size, device="auto", compute_type="int8")
        return _whisper[size]


def transcribe(path, size=None, prompt=None, lang=WHISPER_LANG):
    """Audio file -> (cleaned text, raw text, info dict). `prompt=None` uses the default setting."""
    model = get_whisper(size)
    use_prompt = USE_PROMPT if prompt is None else bool(prompt)
    t = time.time()
    segments, info = model.transcribe(
        path, language=lang, beam_size=5, vad_filter=True,
        initial_prompt=(prompt if isinstance(prompt, str) else PROMPT + _vocab) if use_prompt else None,
        condition_on_previous_text=False)
    kept = [s.text.strip() for s in segments if not (s.no_speech_prob > 0.6 and s.avg_logprob < -1.0)]
    raw = " ".join(kept).strip()
    if is_hallucination(raw):
        raw = ""
    return clean_transcript(raw), raw, {"language": info.language, "audio_s": round(info.duration, 2),
                                        "asr_ms": int((time.time() - t) * 1000), "model": size or WHISPER_MODEL}


# Whisper's well-known inventions on silence or noise (YouTube outros), Urdu and Hindi/English variants.
HALLUCINATIONS = ["سبسکرائب", "ویڈیو دیکھنے کا شکریہ", "دیکھنے کے لیے شکریہ", "subscribe", "thanks for watching",
                  "like and share", "سننے کا شکریہ"]


def is_hallucination(text):
    t = text.lower()
    return any(h in t for h in HALLUCINATIONS) and len(t.split()) <= 8


DIGIT_WORDS = {
    "صفر": "0", "زیرو": "0", "ایک": "1", "دو": "2", "تین": "3", "چار": "4", "پانچ": "5", "چھ": "6", "چھے": "6",
    "سات": "7", "آٹھ": "8", "نو": "9",
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
    "eight": "8", "nine": "9", "ون": "1", "ٹو": "2", "تھری": "3", "فور": "4", "فائیو": "5", "سکس": "6",
    "سیون": "7", "ایٹ": "8", "نائن": "9",
}
_DW = "|".join(sorted(map(re.escape, DIGIT_WORDS), key=len, reverse=True))
DIGIT_RUN_RE = re.compile(rf"(?<![؀-ۿ\w])(?:{_DW})(?:[\s,،-]+(?:{_DW})){{3,}}(?![؀-ۿ\w])", re.IGNORECASE)
MB_RE = re.compile(r"(?:ایم\s*بی|ایم\s*بے|اِیم\s*بی|\bem\s*bee\b|\bm\.?\s*b\.?)\s*[-،,]?\s*(\d[\d\s]{2,6}\d)", re.IGNORECASE)
DIGIT_GROUPS_RE = re.compile(r"(?<!\d)(\+?\d[\d\s-]{8,16}\d)(?!\d)")


def clean_transcript(text):
    """Make Whisper's output look like what a patient would type, so the NLU rules (phone, MB-xxxx) fire.

    - Urdu/Arabic digits -> 0-9
    - a run of 4+ spoken digit words ("صفر تین صفر صفر ...") -> digits, for phone and booking numbers
    - "ایم بی 1042" / "MB 1 0 4 2" -> "MB-1042"
    - a phone number split into groups ("0300 123 45 67") -> "03001234567"
    - drop the full stop Whisper adds at the end
    """
    if not text:
        return ""
    t = text.translate(URDU_DIGITS)
    t = DIGIT_RUN_RE.sub(lambda m: "".join(DIGIT_WORDS[w.lower()] for w in re.findall(_DW, m.group(0), re.I)), t)
    t = MB_RE.sub(lambda m: "MB-" + re.sub(r"\D", "", m.group(1)), t)

    def join_phone(m):
        digits = re.sub(r"\D", "", m.group(1))
        return digits if (len(digits) == 11 and digits.startswith("03")) or \
            (len(digits) == 12 and digits.startswith("923")) else m.group(0)
    t = DIGIT_GROUPS_RE.sub(join_phone, t)
    t = snap_doctor_names(t)
    t = re.sub(r"\s+", " ", t).strip()
    return t.rstrip("۔.").strip()


# ============================================================================ text -> speech

ONES = ("صفر ایک دو تین چار پانچ چھ سات آٹھ نو دس گیارہ بارہ تیرہ چودہ پندرہ سولہ سترہ اٹھارہ انیس "
        "بیس اکیس بائیس تئیس چوبیس پچیس چھبیس ستائیس اٹھائیس انتیس تیس اکتیس بتیس تینتیس چونتیس پینتیس چھتیس "
        "سینتیس اڑتیس انتالیس چالیس اکتالیس بیالیس تینتالیس چوالیس پینتالیس چھیالیس سینتالیس اڑتالیس انچاس "
        "پچاس اکاون باون ترپن چون پچپن چھپن ستاون اٹھاون انسٹھ ساٹھ اکسٹھ باسٹھ تریسٹھ چونسٹھ پینسٹھ چھیاسٹھ "
        "سڑسٹھ اڑسٹھ انہتر ستر اکہتر بہتر تہتر چوہتر پچھتر چھہتر ستتر اٹھہتر اناسی اسی اکیاسی بیاسی تراسی "
        "چوراسی پچاسی چھیاسی ستاسی اٹھاسی نواسی نوے اکانوے بانوے ترانوے چورانوے پچانوے چھیانوے ستانوے اٹھانوے "
        "ننانوے").split()
assert len(ONES) == 100


def number_words(n):
    if n < 100:
        return ONES[n]
    if n < 1000:
        h, r = divmod(n, 100)
        return f"{ONES[h]} سو" + (f" {ONES[r]}" if r else "")
    if n < 100000:
        k, r = divmod(n, 1000)
        return f"{ONES[k]} ہزار" + (f" {number_words(r)}" if r else "")
    return digit_words(str(n))


def digit_words(s):
    return " ".join(ONES[int(c)] for c in s if c.isdigit())


# Latin words that appear in Urdu replies (names typed in Roman, abbreviations).
LATIN_WORDS = {"dr": "ڈاکٹر", "medbook": "میڈبک", "ent": "ای این ٹی", "ok": "اوکے", "mb": "ایم بی",
               "am": "اے ایم", "pm": "پی ایم", "demo": "ڈیمو", "clinic": "کلینک", "appointment": "اپائنٹمنٹ"}
LETTERS = {"a": "اے", "b": "بی", "c": "سی", "d": "ڈی", "e": "ای", "f": "ایف", "g": "جی", "h": "ایچ", "i": "آئی",
           "j": "جے", "k": "کے", "l": "ایل", "m": "ایم", "n": "این", "o": "او", "p": "پی", "q": "کیو", "r": "آر",
           "s": "ایس", "t": "ٹی", "u": "یو", "v": "وی", "w": "ڈبلیو", "x": "ایکس", "y": "وائی", "z": "زیڈ"}
# Rough Roman Urdu -> Urdu letters for names like "Ali Raza" (longest match first).
ROMAN_MAP = [("sh", "ش"), ("kh", "خ"), ("gh", "غ"), ("ch", "چ"), ("th", "تھ"), ("ph", "ف"), ("aa", "ا"),
             ("ee", "ی"), ("oo", "و"), ("ai", "ے"), ("a", "ا"), ("b", "ب"), ("c", "ک"), ("d", "د"), ("e", "ی"),
             ("f", "ف"), ("g", "گ"), ("h", "ہ"), ("i", "ی"), ("j", "ج"), ("k", "ک"), ("l", "ل"), ("m", "م"),
             ("n", "ن"), ("o", "و"), ("p", "پ"), ("q", "ق"), ("r", "ر"), ("s", "س"), ("t", "ت"), ("u", "و"),
             ("v", "و"), ("w", "و"), ("x", "کس"), ("y", "ی"), ("z", "ز")]


def roman_to_urdu(word):
    w, out, i = word.lower(), "", 0
    while i < len(w):
        for k, v in ROMAN_MAP:
            if w.startswith(k, i):
                # short vowels inside a word are not written in Urdu
                if k in ("a", "e", "i", "u") and 0 < i < len(w) - 1:
                    v = ""
                out, i = out + v, i + len(k)
                break
        else:
            i += 1
    return out


def latin_word(w):
    lw = w.lower()
    if lw in LATIN_WORDS:
        return LATIN_WORDS[lw]
    if w.isupper() and len(w) <= 4:                      # abbreviation: spell it
        return " ".join(LETTERS.get(c, "") for c in lw)
    return roman_to_urdu(w)


def speakable(text):
    """Urdu reply -> text MMS-TTS can read: numbers as words, Latin as Urdu letters, no symbols."""
    t = text.translate(URDU_DIGITS)
    t = re.sub(r"\([^)]*x[^)]*\)", "", t)                                  # (03xx-xxxxxxx) hints
    t = re.sub(r"\bMB-?(\d+)", lambda m: "ایم بی " + digit_words(m.group(1)), t)
    t = re.sub(r"\+?\d[\d-]{6,}\d", lambda m: digit_words(m.group(0)), t)  # phone numbers, 1122-style codes
    t = re.sub(r"\b1122\b", digit_words("1122"), t)
    t = re.sub(r"(\d{1,2}):(\d{2})", lambda m: f"{number_words(int(m.group(1)))} بجے" if m.group(2) == "00"
               else f"{number_words(int(m.group(1)))} بج کر {number_words(int(m.group(2)))} منٹ", t)
    t = re.sub(r"\d+", lambda m: number_words(int(m.group(0))), t)
    t = re.sub(r"[A-Za-z]+", lambda m: latin_word(m.group(0)), t)
    t = re.sub(r"[()\[\]{}\"'*_/:;|<>=+#@&%-]", " ", t)
    t = re.sub(r"\n+", "۔ ", t)
    return re.sub(r"\s+", " ", t).strip()


def get_tts():
    global _tts
    with _lock:
        if _tts is None:
            import torch
            from transformers import AutoTokenizer, VitsModel
            torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
            _tts = (VitsModel.from_pretrained(TTS_MODEL).eval(), AutoTokenizer.from_pretrained(TTS_MODEL))
        return _tts


def can_speak(text):
    return bool(text) and len(ARABIC_RE.findall(text)) > len(re.findall(r"[A-Za-z]", text))


@lru_cache(maxsize=256)
def synthesize(text):
    """Urdu-script text -> WAV bytes (16 kHz mono). Sentences are synthesised one by one and joined with
    a short pause, which keeps long replies clear and lets each piece stay small."""
    import numpy as np
    import soundfile as sf
    import torch
    model, tok = get_tts()
    sr = model.config.sampling_rate
    pause = np.zeros(int(0.25 * sr), dtype=np.float32)
    parts = []
    for sent in re.split(r"(?<=[۔؟!?])\s*", speakable(text)):
        sent = sent.strip(" ۔")
        if not ARABIC_RE.search(sent):
            continue
        torch.manual_seed(0)                       # VITS samples durations: same text, same audio
        with torch.no_grad():
            wav = model(**tok(sent, return_tensors="pt")).waveform[0].numpy()
        parts += [wav, pause]
    if not parts:
        raise ValueError("nothing to say")
    buf = io.BytesIO()
    sf.write(buf, np.concatenate(parts), sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def preload():
    """Load both models in the background so the first voice message is not slow."""
    def run():
        try:
            if asr_available():
                get_whisper()
            if tts_available():
                synthesize("جی")
        except Exception as e:                      # a failed preload just means lazy loading later
            print(f"voice preload failed: {e}")
    threading.Thread(target=run, daemon=True).start()
