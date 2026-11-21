"""Symptom-to-department backstop: body-part and complaint keywords in Urdu script, Roman Urdu and English.

Why: the XLM-R department head is weakest on natural Urdu-script symptoms (only template phrasing was seen in
training) and is over-confident when wrong (e.g. "گلے میں درد ہے اور بخار" -> cardiology at 1.00). A complaint
that names an organ is a strong, explainable signal, so the dialogue manager combines the two:

    1. a stated age of 12 or under, or a child word (beta, beti, بچے, chota bhai) with no age
                                                            -> pediatrics (unless a gynecology word is present)
    2. exactly one specialist department has keyword hits  -> that department
    3. only general complaints (fever, cough, weakness)     -> general physician
    4. no hits, or two specialists tie                       -> keep the model's answer

The keyword lists were written from general medical vocabulary and the training lexicon (data_gen/lexicons.py),
not from the test sets. They should still be checked by a doctor, like the lexicon itself.
"""
import re

# Roman / English patterns use \b on both sides; Urdu patterns use \b too (Python treats Urdu letters as \w),
# so کان does not match inside دکان. Stems end in \w* where Urdu/Roman inflect (گلا / گلے, ghutna / ghutne).
SPECIALIST = {
    "cardiology": [
        r"\bdil\b", r"heart", r"seen[ae]y?\b", r"chest", r"dhar?kan", r"palpitation", r"\bbp\b", r"blood ?pressure",
        r"saans? phool", r"baa?yei?n baazu",
        r"\bدل\b", r"\bسین[ہے]\b", r"دھڑکن", r"بلڈ ?پریشر", r"\bبی پی\b", r"سانس پھول", r"بائیں بازو",
    ],
    "dermatology": [
        r"\bskin\b", r"\bjild\b", r"kh?arish", r"itch", r"daane?\b", r"pimple", r"acne", r"rash", r"eczema",
        r"baal gir", r"hair ?fall", r"dandruff", r"nakh?o?o?n\b", r"\bnail", r"chehre? (pe|par) daag", r"dhabb?e",
        r"\bجلد\b", r"خارش", r"دان[ےا]", r"\bکیل\b", r"مہاس[ےا]", r"بال گر", r"خشکی", r"ناخن", r"(?<!م)داغ", r"دھب[ےا]",
        r"\bسکن\b", r"الرجی.{0,12}(جلد|چہر)", r"(جلد|چہر).{0,12}الرجی",
    ],
    "ent": [
        r"\bkaa?n\b", r"\bears?\b", r"\bnaa?k\b", r"\bnose\b", r"\bgal[ae]y?\b", r"\bgale\b", r"throat", r"tonsil",
        r"awaa?z", r"\bvoice\b", r"sinus", r"nakse?e?r", r"nigal", r"swallow", r"behr[ae]", r"sunai",
        r"\bکان\b", r"\bناک\b", r"\bگل[اےہ]\b", r"\bحلق\b", r"ٹانسل", r"آواز", r"سائنس", r"نکسیر", r"\bنگل", r"سنائی",
    ],
    "gastroenterology": [
        r"\bpa[ei]t\b", r"\bpet\b", r"stomach", r"tummy", r"maid[ae]y?\b", r"\bulti", r"vomit", r"\bdast\b",
        r"diarrh", r"\bqabz", r"constipat", r"acidity", r"\bgas\b", r"dakaa?r", r"burp", r"jalan", r"heartburn",
        r"hazam", r"digest", r"jigar", r"liver", r"piliya", r"jaundice", r"ulcer", r"bhook nahi",
        r"\bپیٹ\b", r"معد[ےہ]", r"الٹی", r"\bدست\b", r"قبض", r"تیزابیت", r"\bگیس\b", r"ڈکار", r"جلن", r"ہضم",
        r"\bجگر\b", r"یرقان", r"بھوک نہیں",
    ],
    "orthopedics": [
        r"ghutn", r"\bknee", r"kamar", r"back ?pain", r"hadd?i", r"\bbone", r"\bjo+r(on)?\b", r"joint",
        r"gardan", r"\bneck\b", r"kandh", r"shoulder", r"\bmoch\b", r"sprain", r"\beri\b", r"heel", r"kalai",
        r"wrist", r"fracture", r"sciatica", r"tang (mein|me) dard", r"\bleg\b",
        r"گھٹن", r"\bکمر\b", r"ہڈی", r"ہڈیوں", r"جوڑ", r"گردن", r"کندھ", r"موچ", r"ایڑی", r"کلائی", r"ٹانگ",
    ],
    "gynecology": [
        r"period", r"mahwari", r"menstru", r"pregnan", r"\bhamal\b", r"delivery", r"\bpcos\b", r"ultrasound",
        r"ماہواری", r"\bحمل\b", r"ڈیلیوری", r"حاملہ",
    ],
}
GENERAL = [
    r"bukh?aa?r", r"fever", r"nazla", r"zukaa?m", r"\bflu\b", r"\bcold\b", r"kh?aa?nsi", r"cough", r"kamzori",
    r"weakness", r"thakaa?wa?t", r"tired", r"sar ?(mein |me )?dard", r"headache", r"chakk?ar", r"dizz",
    r"sugar", r"diabet", r"typhoid", r"body ?pain", r"jism (mein|me) dard", r"chills",
    r"بخار", r"نزلہ", r"زکام", r"کھانسی", r"کمزوری", r"تھکاوٹ", r"سر ?(میں )?درد", r"چکر", r"شوگر", r"ٹائیفائیڈ",
    r"جسم (میں )?درد", r"\bفلو\b",
]
CHILD_WORDS = [r"chh?ot[aei] (bhai|behan|bahen)", r"چھوٹ[ےیا] (بھائی|بہن)", r"\bbet[ae]\b", r"\bbeti\b", r"bach(ay|e|on|a|ey|chay|che)\b", r"\bbaby\b", r"\bchild", r"\bkid",
               r"\bson\b", r"\bdaughter", r"\bbhanj", r"\bbhatij", r"\bnavas", r"\bpot[ae]\b|\bpoti\b",
               r"\bبیٹ[اے]\b", r"\bبیٹی\b", r"\bبچ[ےہ]\b", r"\bبچوں\b", r"\bبچی\b", r"بھانج", r"بھتیج", r"\bنواس", r"\bپوت"]
# covers the training lexicon's CHILD phrases ("mere bete", "میری بیٹی") and common family words

_SPEC = {d: re.compile("|".join(f"(?:{p})" for p in pats), re.I) for d, pats in SPECIALIST.items()}
_GEN = re.compile("|".join(f"(?:{p})" for p in GENERAL), re.I)
_CHILD = re.compile("|".join(f"(?:{p})" for p in CHILD_WORDS), re.I)


AGE_RE = re.compile(r"(\d{1,3}|[\u0600-\u06FF]+|[a-z]+)\s*(saal|sal|years?|yrs?|سال|mahine|months?|مہینے)", re.I)


def age_years(text):
    """Age in years if the message states one ('5 saal', 'پچیس سال', '6 mahine'), else None."""
    from normalize import NUM_WORDS, URDU_DIGITS
    words = {**NUM_WORDS, "بیس": 20, "پچیس": 25, "تیس": 30, "پینتیس": 35, "چالیس": 40, "پینتالیس": 45,
             "پچاس": 50, "ساٹھ": 60, "ستر": 70, "do": 2}
    for m in AGE_RE.finditer(text.translate(URDU_DIGITS)):
        n = int(m.group(1)) if m.group(1).isdigit() else words.get(m.group(1).lower())
        if n is None:
            continue
        return n / 12 if m.group(2).lower() in ("mahine", "month", "months", "مہینے") else n
    return None


CHILD_MAX_AGE = 12


def keyword_department(text):
    """(department or None, reason). None means: no clear keyword signal, use the model."""
    hits = {d: [m.group(0) for m in rx.finditer(text)] for d, rx in _SPEC.items()}
    hits = {d: h for d, h in hits.items() if h}
    general = [m.group(0) for m in _GEN.finditer(text)]
    child = _CHILD.search(text)
    age = age_years(text)
    if (hits or general) and "gynecology" not in hits:
        if age is not None and age <= CHILD_MAX_AGE:
            return "pediatrics", f"age {age:g}"
        if child and age is None:
            return "pediatrics", f"child word '{child.group(0)}'"
    if len(hits) == 1:
        d, h = next(iter(hits.items()))
        return d, f"keywords {h}"
    if len(hits) > 1:
        return None, f"several departments {sorted(hits)}"
    if general:
        return "general_physician", f"general complaint {general}"
    return None, "no keywords"


def route(text, model_dept, model_conf, min_conf=0.40):
    """Combine keywords and the model. Returns (department, source, explanation).
    source: 'keywords' when the keywords decided, 'model' when the model did, 'fallback' when neither is sure."""
    kd, why = keyword_department(text)
    if kd:
        if kd == model_dept:
            return kd, "model", f"model {model_dept} ({model_conf:.2f}) agrees with {why}"
        return kd, "keywords", f"{why} -> {kd} (model said {model_dept} {model_conf:.2f})"
    if model_dept and model_conf >= min_conf:
        return model_dept, "model", f"model {model_dept} ({model_conf:.2f}); {why}"
    return "general_physician", "fallback", f"model {model_dept} ({model_conf:.2f}) below {min_conf}; {why}"
