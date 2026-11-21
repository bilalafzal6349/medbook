"""Turn DATE and TIME slot strings (Roman Urdu, Urdu script, English) into calendar values.

The NLU model only finds the span ("agle somwar", "ساڑھے نو بجے", "after 4"). The dialogue
manager needs a real date and a time window to search the schedule, so this module maps
spans to:

    parse_date(text, today) -> DateValue(start, end, exact)   (end inclusive; exact = one day)
    parse_time(text)        -> TimeValue(start_min, end_min, exact, label)

Returns None when the text cannot be understood, so the bot asks again instead of guessing.
All rules are deterministic, so every decision can be explained in the report.
"""
import re
from dataclasses import dataclass
from datetime import date, timedelta

# ----------------------------------------------------------------------------- helpers

URDU_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

# number words up to 31 (dates) / 12 (clock). Urdu script and Roman Urdu.
NUM_WORDS = {
    # urdu script
    "ایک": 1, "یکم": 1, "دو": 2, "تین": 3, "چار": 4, "پانچ": 5, "چھ": 6, "چھے": 6, "سات": 7, "آٹھ": 8,
    "نو": 9, "دس": 10, "گیارہ": 11, "بارہ": 12, "تیرہ": 13, "چودہ": 14, "پندرہ": 15, "سولہ": 16,
    "سترہ": 17, "اٹھارہ": 18, "انیس": 19, "بیس": 20, "اکیس": 21, "بائیس": 22, "تئیس": 23, "چوبیس": 24,
    "پچیس": 25, "چھبیس": 26, "ستائیس": 27, "اٹھائیس": 28, "انتیس": 29, "تیس": 30, "اکتیس": 31,
    # roman urdu (only words that do not collide with common Roman words)
    "ek": 1, "teen": 3, "chaar": 4, "char": 4, "paanch": 5, "panch": 5, "chhe": 6, "chay": 6,
    "saat": 7, "aath": 8, "nau": 9, "das": 10, "gyarah": 11, "gyara": 11, "barah": 12, "bara": 12,
    # english
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12,
}

WEEKDAYS = {  # Monday = 0
    0: ["monday", "mon", "somwar", "somvar", "peer", "pir", "پیر", "سوموار", "سوموار"],
    1: ["tuesday", "tue", "tues", "mangal", "mangalwar", "منگل"],
    2: ["wednesday", "wed", "budh", "budhwar", "بدھ"],
    3: ["thursday", "thu", "thurs", "jumeraat", "jumerat", "jumairat", "جمعرات"],
    4: ["friday", "fri", "jumma", "juma", "jumah", "jummah", "jumme", "jumay", "جمعہ", "جمعے"],
    5: ["saturday", "sat", "hafta", "haftay", "ہفتہ", "ہفتے"],
    6: ["sunday", "sun", "itwaar", "itwar", "itvaar", "اتوار"],
}
WEEKDAY_OF = {w: d for d, ws in WEEKDAYS.items() for w in ws}

MONTHS = {
    1: ["january", "jan", "جنوری"], 2: ["february", "feb", "فروری"], 3: ["march", "mar", "مارچ"],
    4: ["april", "apr", "اپریل"], 5: ["may", "مئی"], 6: ["june", "jun", "جون"],
    7: ["july", "jul", "جولائی"], 8: ["august", "aug", "اگست"], 9: ["september", "sep", "sept", "ستمبر"],
    10: ["october", "oct", "اکتوبر"], 11: ["november", "nov", "نومبر"], 12: ["december", "dec", "دسمبر"],
}
MONTH_OF = {w: m for m, ws in MONTHS.items() for w in ws}

NEXT_WORDS = {"agle", "agla", "agli", "next", "aglay", "اگلے", "اگلا", "اگلی"}
THIS_WORDS = {"is", "isi", "this", "iss", "اس", "اسی"}

TOKEN_RE = re.compile(r"\d{1,2}:\d{2}|[\w/]+|[^\w\s]")


def _tokens(text):
    text = text.translate(URDU_DIGITS).lower()
    text = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", text)
    return TOKEN_RE.findall(text)


def _num(tok):
    if tok.isdigit():
        return int(tok)
    return NUM_WORDS.get(tok)


# ----------------------------------------------------------------------------- dates

@dataclass
class DateValue:
    start: date
    end: date            # inclusive
    text: str = ""

    @property
    def exact(self):
        return self.start == self.end


def _next_weekday(today, wd, strictly_after=False):
    delta = (wd - today.weekday()) % 7
    if delta == 0 and strictly_after:
        delta = 7
    return today + timedelta(days=delta)


def _day_of_month(today, day, month=None):
    """Next date with this day number (this month if not past, else next month)."""
    y, m = today.year, month or today.month
    for _ in range(13):
        try:
            d = date(y, m, day)
        except ValueError:
            d = None
        if d and d >= today:
            return d
        if month:            # explicit month in the past -> next year
            y += 1
        else:
            m += 1
            if m > 12:
                m, y = 1, y + 1
    return None


def parse_date(text, today):
    """Map a DATE span to a date or a date range. None if not understood."""
    if not text:
        return None
    raw = text
    toks = _tokens(text)
    s = " ".join(toks)

    def one(d):
        return DateValue(d, d, raw)

    # ---- fixed words
    if re.search(r"\b(day after tomorrow|parson|parsoon|parso)\b", s) or "پرسوں" in s or "پرسو" in s:
        return one(today + timedelta(days=2))
    if re.search(r"\b(aaj|aj|today|abhi)\b", s) or "آج" in s:
        return one(today)
    if re.search(r"\b(kal|kl|tomorrow|tmrw|tomorow)\b", s) or "کل" in toks:
        return one(today + timedelta(days=1))

    # ---- "N din baad" / "after N days"
    m = re.search(r"(\w+) (din|days?|دن) (baad|bad|بعد|later)", s) or re.search(r"after (\w+) days?", s)
    if m and (_num(m.group(1)) or m.group(1) == "do"):
        return one(today + timedelta(days=_num(m.group(1)) or 2))

    has_next = any(t in NEXT_WORDS for t in toks)
    has_this = any(t in THIS_WORDS for t in toks)

    # ---- weekday ("agle somwar", "is jumme", "Friday")
    # "hafta"/"ہفتہ" is both Saturday and "week": treat it as week when it follows agle/is.
    week_words = {"hafte", "haftay", "week", "ہفتے", "hafta", "ہفتہ"}
    for i, t in enumerate(toks):
        if t in WEEKDAY_OF:
            if t in week_words and i > 0 and (toks[i - 1] in NEXT_WORDS or toks[i - 1] in THIS_WORDS):
                continue
            return one(_next_weekday(today, WEEKDAY_OF[t], strictly_after=has_next))

    # ---- week / month ranges
    if any(t in week_words for t in toks):
        if has_next:   # next Monday .. next Saturday
            start = _next_weekday(today, 0, strictly_after=True)
            return DateValue(start, start + timedelta(days=5), raw)
        return DateValue(today, today + timedelta(days=(5 - today.weekday()) % 7), raw)  # rest of this week
    if any(t in ("mahine", "mahinay", "month", "مہینے") for t in toks):
        if has_next:
            m1 = date(today.year + (today.month == 12), today.month % 12 + 1, 1)
            m2 = date(m1.year + (m1.month == 12), m1.month % 12 + 1, 1) - timedelta(days=1)
            return DateValue(m1, m2, raw)
        m2 = date(today.year + (today.month == 12), today.month % 12 + 1, 1) - timedelta(days=1)
        return DateValue(today, m2, raw)

    # ---- numeric d/m or d/m/y
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", s)
    if m:
        d_, mo = int(m.group(1)), int(m.group(2))
        if 1 <= d_ <= 31 and 1 <= mo <= 12:
            return one(_day_of_month(today, d_, mo)) if _day_of_month(today, d_, mo) else None

    # ---- "25 tareekh", "2 December", "پچیس تاریخ", "یکم دسمبر", "28 Nov"
    day, month = None, None
    for i, t in enumerate(toks):
        if t in MONTH_OF:
            month = MONTH_OF[t]
        n = _num(t)
        if n and 1 <= n <= 31 and day is None:
            nxt = toks[i + 1] if i + 1 < len(toks) else ""
            prv = toks[i - 1] if i > 0 else ""
            if nxt in ("tareekh", "tarikh", "tareek", "تاریخ", "date") or nxt in MONTH_OF or prv in MONTH_OF \
                    or t.isdigit():
                day = n
    if day:
        d = _day_of_month(today, day, month)
        return one(d) if d else None
    return None


# ----------------------------------------------------------------------------- times

@dataclass
class TimeValue:
    start: int           # minutes after midnight, inclusive
    end: int             # exclusive
    text: str = ""
    exact: bool = False  # True when one clock time was asked for
    pick: str = ""       # "first" / "last" for "first slot" / "last slot"


PARTS = [  # (words, start, end, pm_hint)
    (["subah sawere", "subha sawere", "early morning", "صبح سویرے"], 9 * 60, 10 * 60, False),
    (["subah", "subha", "sobah", "morning", "صبح", "am"], 9 * 60, 12 * 60, False),
    (["dopahar", "dopehar", "dupehar", "afternoon", "noon", "دوپہر"], 12 * 60, 16 * 60, True),
    (["shaam", "sham", "evening", "شام", "pm"], 16 * 60, 20 * 60, True),
    (["raat", "rat", "night", "رات"], 19 * 60, 21 * 60, True),
]
FRACTIONS = {  # "saade 9" = 9:30, "sawa 4" = 4:15, "paune 6" = 5:45
    "saade": 30, "sarhe": 30, "sadhe": 30, "saarhe": 30, "ساڑھے": 30,
    "sawa": 15, "سوا": 15,
    "paune": -15, "pone": -15, "پونے": -15,
}
SPECIAL = {"dhai": (2, 30), "dedh": (1, 30), "ڈھائی": (2, 30), "ڈیڑھ": (1, 30)}
AFTER_WORDS = {"baad", "bad", "after", "بعد"}
BEFORE_WORDS = {"pehle", "pehlay", "before", "پہلے", "tak"}
DAY_OPEN, DAY_CLOSE = 9 * 60, 21 * 60


def _to24(h, pm_hint, am_hint):
    if pm_hint and h < 12:
        return h + 12
    if am_hint:
        return h % 12
    if 1 <= h <= 7:          # clinic is closed at night, so "5 baje" means 5 pm
        return h + 12
    return h


def _clock_values(toks, s):
    """All clock times in the text, as minutes, in order."""
    out = []
    i = 0
    while i < len(toks):
        t = toks[i]
        frac = FRACTIONS.get(t)
        if frac is not None and i + 1 < len(toks) and _num(toks[i + 1]):
            h = _num(toks[i + 1])
            out.append(((h * 60 + frac) if frac > 0 else (h * 60 + frac), i))
            i += 2
            continue
        if t in SPECIAL:
            h, mn = SPECIAL[t]
            out.append((h * 60 + mn, i))
            i += 1
            continue
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", t)
        if m:
            out.append((int(m.group(1)) * 60 + int(m.group(2)), i))
            i += 1
            continue
        n = _num(t)
        if n and 1 <= n <= 12:
            nxt = toks[i + 1] if i + 1 < len(toks) else ""
            # a bare number counts as a time inside a TIME span ("after 4", "11 baje")
            if nxt in ("baje", "bje", "bjy", "bajay", "بجے", "am", "pm", "o", "se", "ke", "tak") or len(toks) <= 3 \
                    or (i > 0 and toks[i - 1] in AFTER_WORDS | BEFORE_WORDS):
                out.append((n * 60, i))
        i += 1
    return out


def parse_time(text):
    """Map a TIME span to a window of minutes. None if not understood."""
    if not text:
        return None
    raw = text
    s_raw = text.translate(URDU_DIGITS).lower()
    s_raw = re.sub(r"(\d)\s*(am|pm)\b", r"\1 \2", s_raw)
    toks = TOKEN_RE.findall(s_raw)
    s = " ".join(toks)

    if re.search(r"\b(first|pehla|pehli|sab se pehle|earliest)\b", s) and "slot" in s or "پہلا" in s:
        return TimeValue(DAY_OPEN, DAY_CLOSE, raw, pick="first")
    if re.search(r"\b(last|aakhri|akhri)\b", s) or "آخری" in s:
        return TimeValue(DAY_OPEN, DAY_CLOSE, raw, pick="last")
    if re.search(r"\b(zuhr|zohar|zohr|zuhar)\b", s) or "ظہر" in s:
        return TimeValue(13 * 60 + 30, 16 * 60, raw)
    if re.search(r"\b(asr|asar)\b", s) or "عصر" in s:
        return TimeValue(16 * 60 + 30, 19 * 60, raw)

    part = None
    for words, a, b, pm in PARTS:
        if any((" " in w and w in s) or (" " not in w and w in toks) for w in words):
            part = (a, b, pm, words[0] == "subah" or words[0] == "subah sawere")
            break
    pm_hint = bool(part and part[2]) or "pm" in toks
    am_hint = bool(part and part[3]) or "am" in toks

    clocks = _clock_values(toks, s)
    mins = []
    for v, _ in clocks:
        h, mn = divmod(v, 60)
        mins.append(_to24(h, pm_hint, am_hint) * 60 + mn)

    after = any(t in AFTER_WORDS for t in toks)
    before = any(t in BEFORE_WORDS for t in toks)
    between = len(mins) >= 2 and any(t in ("beech", "darmiyan", "between", "درمیان", "بیچ", "se", "to", "سے")
                                     for t in toks)
    if between:
        a, b = sorted(mins[:2])
        return TimeValue(a, b + 1 if b == a else b, raw)
    if mins and after and not before:
        return TimeValue(mins[0], DAY_CLOSE, raw)
    if mins and before:
        return TimeValue(DAY_OPEN, mins[0], raw)
    if mins:
        return TimeValue(mins[0], mins[0] + 1, raw, exact=True)
    if part:
        return TimeValue(part[0], part[1], raw)
    if re.search(r"\b(koi bhi|any|kabhi bhi|jab bhi|jo bhi|anytime)\b", s) or "کوئی بھی" in s:
        return TimeValue(DAY_OPEN, DAY_CLOSE, raw)
    return None


ANY_TIME_RE = re.compile(r"\b(koi bhi|any ?time|any|kabhi bhi|jab bhi|jo bhi|kisi bhi waqt|koi masla nahi)\b|کوئی بھی|جب بھی")
