"""Template-based generator for code-switched Urdu/English clinic utterances.

Usage:
    python generate.py --per-template 40 --out ../data/synthetic --seed 13

Writes train/val/test JSONL files. Every row:
    {"id", "text", "tokens", "tags", "spans", "intent", "department",
     "script", "style", "source", "template_id"}
Splits are made BY TEMPLATE, so test templates are never seen in training.
"""
import argparse
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

import lexicons as L
from schema import DEPARTMENTS, INTENTS, NO_DEPARTMENT, SLOTS
from templates import TEMPLATES

TOKEN_RE = re.compile(r"\w+(?:[-:]\w+)*|[^\w\s]")
PLACEHOLDER_RE = re.compile(r"\{([A-Z_]+)\}")
ARABIC_RE = re.compile(r"[؀-ۿ]")
LATIN_RE = re.compile(r"[A-Za-z]")
ROUTED_INTENTS = {"book_appointment", "describe_symptom", "doctor_availability"}

# Roman Urdu spelling variants seen in real chats (word -> alternatives)
ROMAN_VARIANTS = {
    "chahiye": ["chahye", "chaiye", "chahie", "chaheye"], "hai": ["he", "hy", "h"],
    "mujhe": ["mjhe", "mujhay", "mujy"], "kal": ["kl"], "appointment": ["apointment", "appt", "apt"],
    "doctor": ["dr", "docter", "dctr"], "kar": ["kr"], "dein": ["den", "dain", "do"],
    "please": ["plz", "pls"], "plz": ["pls", "please"], "nahi": ["nai", "nhi", "nahin"],
    "theek": ["thk", "theak", "thik"], "mein": ["main", "me", "mai"], "baje": ["bjy", "bje"],
    "subah": ["subha", "sobah"], "shaam": ["sham"], "raha": ["rha"], "kaan": ["kan"],
    "seene": ["seenay", "sene"], "dard": ["dard"], "bukhar": ["bukhaar", "bokhar"],
}


def script_of(text: str) -> str:
    has_ar, has_lat = bool(ARABIC_RE.search(text)), bool(LATIN_RE.search(text))
    if has_ar and has_lat:
        return "mixed"
    return "urdu" if has_ar else "roman"


# Roman-Urdu words; a roman lexicon item with none of these is treated as English
# (so it can appear inside an Urdu-script "mixed" sentence).
ROMAN_MARKERS = set("""ka ke ki wale wala mein pe se ko dil jild kaan naak gala pait maiday haddiyon haddi jor
aam aurton bachon mahir seene dard bukhar nazla zukam kamzori jism khansi thakawat sar chakkar barh gayi halka
dharkan tez saans phoolna ghabrata hai kam bojh seedhi chadhne phoolti baayein baazu daane kharish baal girna
chehre daag dhabbe nakhun khushk behna naksir awaaz baith seeti nigalne takleef ulti dast qabz jalan bhook nahi
lagti khatti dakaarein phoolna jigar masla piliya ghutne kamar toot joron gardan kandhe moch aa eri haath
mahwari zyada band sugar kal parson aaj agle hafte jumma tareekh somwar mangal budh jumeraat hafta itwaar is
jumme mahine do teen din baad subah shaam dopahar raat baje saade sawere dhai paune beech pehle zuhr""".split())


def is_english(item: str) -> bool:
    return not any(w.lower().strip(".") in ROMAN_MARKERS for w in item.split())


def pool_for(lex: dict, style: str):
    if style == "roman":
        return lex.get("roman", []) + lex.get("en", [])
    if style == "urdu":
        return lex["urdu"]
    english = lex.get("en", []) + [x for x in lex.get("roman", []) if is_english(x)]
    return lex["urdu"] + english  # mixed


def pick(rng, lex: dict, style: str) -> str:
    return rng.choice(pool_for(lex, style))


PREFIX = {
    "roman": ["AoA ", "assalam o alaikum, ", "hello, ", "ji ", "sir ", "bhai ", "madam ", "hi, ", "excuse me, "],
    "urdu": ["السلام علیکم، ", "جی ", "سر ", "بھائی ", "میڈم "],
    "mixed": ["hello، ", "السلام علیکم، ", "sir ", "hi، ", "جی "],
}
SUFFIX = {
    "roman": [" please", " plz", " shukriya", " jaldi bata dein", " thanks", " ji", " meherbani hogi"],
    "urdu": [" شکریہ", " مہربانی", " جلدی بتا دیں", " جی", " مہربانی ہو گی"],
    "mixed": [" please", " thanks", " شکریہ", " plz", " جی"],
}
NO_WRAP = {"greet", "goodbye", "inform", "emergency"}


# Template words that rule out a department: a male patient or male speaker is never routed to gynecology,
# and ammi / abbu are never routed to pediatrics.
MALE_RE = re.compile(r"\babbu\b|ابو|\bchahta\b|\bsakta\b|چاہتا|سکتا|سکوں گا", re.I)
ADULT_RE = re.compile(r"\bammi\b|\babbu\b|امی|ابو", re.I)


def fill(rng, tpl_text: str, style: str):
    """Fill placeholders. Returns text, char spans [(start, end, SLOT)], department.

    Department rules (same as backend/routing.py):
      - a CHILD phrase with no age, or an age of 12 or under -> pediatrics
      - a CHILD phrase with an age over 12 -> the adult department of the symptom
        ("mere chote bhai ki umar 25 saal hai, usay dast hai" -> gastroenterology)
      - otherwise the department of the symptom / doctor / named department
    """
    names = PLACEHOLDER_RE.findall(tpl_text)
    banned = set()
    if MALE_RE.search(tpl_text):
        banned.add("gynecology")
    if ADULT_RE.search(tpl_text):
        banned.add("pediatrics")
    if "SYMPTOM" in names:
        target = rng.choice([d for d in L.SYMPTOMS if d not in banned])
    elif "CHILD" in names:
        target = "pediatrics"
    else:
        target = rng.choice([d for d in DEPARTMENTS if d not in banned])

    fixed = {}  # values chosen up front because the department depends on them
    dept = None
    if "CHILD" in names:
        cstyle = "urdu" if style == "mixed" else style
        years = None
        if "AGE" in names:
            fixed["AGE"] = pick(rng, L.AGE, style)
            years = L.age_in_years(fixed["AGE"])
        if years is not None and years > L.CHILD_MAX_AGE:
            fixed["CHILD"] = rng.choice(L.CHILD_CAN_BE_ADULT[cstyle])
            fixed["CSYMPTOM"] = pick(rng, L.CHILD_SYMPTOMS, style)
            dept = L.CHILD_SYMPTOM_ADULT_DEPT[fixed["CSYMPTOM"]]
        else:
            pool = L.CHILD[cstyle]
            if years is not None:
                pool = [c for c in pool if c not in L.CHILD_WITH_AGE]
            fixed["CHILD"] = rng.choice(pool)
            dept = "pediatrics"

    def value_for(slot):
        nonlocal dept
        if slot in fixed:
            return fixed.pop(slot)
        if slot == "DOCTOR":
            dnames, d = rng.choice([x for x in L.DOCTORS if x[1] == target])
            dept = dept or d
            if style == "urdu" or (style == "mixed" and rng.random() < 0.5):
                return dnames["urdu"]
            short = L.DOCTOR_SHORT_ROMAN.get(dnames["roman"])
            return rng.choice(short) if short and rng.random() < 0.3 else dnames["roman"]
        if slot == "DEPARTMENT":
            dept = dept or target
            return pick(rng, L.DEPARTMENT_NAMES[target], style)
        if slot == "SYMPTOM":
            dept = dept or target
            return pick(rng, L.SYMPTOMS[target], style)
        if slot == "CSYMPTOM":
            return pick(rng, L.CHILD_SYMPTOMS, style)
        if slot == "CHILD":
            return pick(rng, L.CHILD, "urdu" if style == "mixed" else style)
        if slot == "EMERGENCY":
            return pick(rng, L.EMERGENCY, "urdu" if style == "mixed" else style)
        if slot == "PATIENT_NAME" and target == "gynecology":
            return rng.choice([x for x in pool_for(L.PATIENT_NAME, style) if x in L.FEMALE_NAMES])
        return pick(rng, getattr(L, slot), style)

    def repeats_next_words(val, after):
        """'{TIME} ke baad' with TIME='Zuhr ke baad' would give 'Zuhr ke baad ke baad'."""
        v, nxt = val.lower().split(), after.lower().split()
        return len(v) >= 2 and nxt[:2] == v[-2:]

    out, spans, pos, used = [], [], 0, set()
    for m in PLACEHOLDER_RE.finditer(tpl_text):
        out.append(tpl_text[pos:m.start()])
        slot = m.group(1)
        val = value_for(slot)
        for _ in range(8):  # avoid "Monday nahi Monday" style repeats
            if val not in used and not repeats_next_words(val, tpl_text[m.end():]):
                break
            val = value_for(slot)
        used.add(val)
        start = sum(len(s) for s in out)
        out.append(val)
        label = "SYMPTOM" if slot == "CSYMPTOM" else slot
        if label in SLOTS:
            spans.append((start, start + len(val), label))
        pos = m.end()
    out.append(tpl_text[pos:])
    return "".join(out), spans, dept


def wrap(rng, text, spans, style, intent):
    """Random greeting prefix / politeness suffix; shifts spans."""
    if intent in NO_WRAP:
        return text, spans
    first = text.split()[0].lower() if text.split() else ""
    last = text.split()[-1].lower() if text.split() else ""
    if rng.random() < 0.2:
        p = rng.choice(PREFIX[style])
        if p.strip(" ,،").lower() != first:  # no "ji ji haan"
            text = p + text
            spans = [(s + len(p), e + len(p), l) for s, e, l in spans]
    if rng.random() < 0.2 and not text.endswith("?") and not text.endswith("؟"):
        sfx = rng.choice(SUFFIX[style])
        if sfx.strip().lower() != last:  # no "nahi ji ji"
            text = text + sfx
    return text, spans


def tokens_and_tags(text: str, spans):
    tokens, tags = [], []
    for m in TOKEN_RE.finditer(text):
        tag = "O"
        for s, e, slot in spans:
            if m.start() >= s and m.end() <= e:
                tag = ("B-" if m.start() == s or not tags or not tags[-1].endswith(slot) else "I-") + slot
                break
        tokens.append(m.group())
        tags.append(tag)
    return tokens, tags


def add_noise(rng, tokens, tags):
    """Roman-only chat noise that keeps the token count (so tags stay aligned)."""
    new = []
    for tok in tokens:
        low = tok.lower()
        if low in ROMAN_VARIANTS and rng.random() < 0.5:
            tok = rng.choice(ROMAN_VARIANTS[low])
        elif LATIN_RE.search(tok) and len(tok) > 4 and rng.random() < 0.08:
            i = rng.randrange(1, len(tok) - 1)  # drop one inner character
            tok = tok[:i] + tok[i + 1:]
        new.append(tok)
    if rng.random() < 0.6:
        new = [t.lower() for t in new]
    keep = [i for i, t in enumerate(new) if not (t in {",", ".", "?", "!"} and rng.random() < 0.7)]
    return [new[i] for i in keep], [tags[i] for i in keep]


def spans_from_tokens(tokens, tags):
    """Rebuild text and char spans from (possibly noised) tokens."""
    text, spans, cur = "", [], None
    for tok, tag in zip(tokens, tags):
        if text and not re.fullmatch(r"[,.?!،؟]", tok):
            text += " "
        start = len(text)
        text += tok
        if tag.startswith("B-"):
            cur = [start, len(text), tag[2:]]
            spans.append(cur)
        elif tag.startswith("I-") and cur:
            cur[1] = len(text)
        else:
            cur = None
    return text, [tuple(s) for s in spans]


def split_templates(rng, val_frac=0.1, test_frac=0.15):
    """Hold out whole templates, per (intent, style) group, so every split has every style."""
    by_intent = defaultdict(list)
    for tid, intent, style, _ in TEMPLATES:
        by_intent[(intent, style)].append(tid)
    assign = {}
    for intent, tids in by_intent.items():
        tids = sorted(tids)
        rng.shuffle(tids)
        n = len(tids)
        n_test = max(1, round(n * test_frac)) if n >= 3 else 0
        n_val = max(1, round(n * val_frac)) if n >= 5 else 0
        for i, t in enumerate(tids):
            assign[t] = "test" if i < n_test else "val" if i < n_test + n_val else "train"
    return assign


def generate(per_template: int, seed: int, noise_frac: float):
    rng = random.Random(seed)
    rows, seen = [], set()
    for tid, intent, style, tpl in TEMPLATES:
        assert intent in INTENTS, intent
        has_slots = bool(PLACEHOLDER_RE.search(tpl))
        n = per_template if has_slots else 6  # fixed phrases: a few wrapped/noised copies
        tries = 0
        made = 0
        while made < n and tries < n * 5:
            tries += 1
            text, spans, dept = fill(rng, tpl, style)
            text, spans = wrap(rng, text, spans, style, intent)
            if text in seen:
                continue
            seen.add(text)
            tokens, tags = tokens_and_tags(text, spans)
            source = "template"
            if style == "roman" and rng.random() < noise_frac:
                tokens, tags = add_noise(rng, tokens, tags)
                text, spans = spans_from_tokens(tokens, tags)
                source = "noise"
            rows.append({
                "id": f"{tid}-{made:04d}",
                "text": text,
                "tokens": tokens,
                "tags": tags,
                "spans": [{"start": s, "end": e, "label": l, "value": text[s:e]} for s, e, l in spans],
                "intent": intent,
                "department": (dept or NO_DEPARTMENT) if intent in ROUTED_INTENTS else NO_DEPARTMENT,
                "script": script_of(text),
                "style": style,
                "source": source,
                "template_id": tid,
            })
            made += 1
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-template", type=int, default=30)
    ap.add_argument("--noise-frac", type=float, default=0.25)
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--out", default="../data/dataset_v2")
    args = ap.parse_args()

    rows = generate(args.per_template, args.seed, args.noise_frac)
    assign = split_templates(random.Random(args.seed))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    files = {k: open(out / f"{k}.jsonl", "w", encoding="utf-8") for k in ("train", "val", "test")}
    counts = Counter()
    for r in rows:
        split = assign[r["template_id"]]
        files[split].write(json.dumps(r, ensure_ascii=False) + "\n")
        counts[split] += 1
    for f in files.values():
        f.close()

    print(f"{len(rows)} rows -> {dict(counts)}")
    print("by intent:", dict(Counter(r["intent"] for r in rows)))
    print("by script:", dict(Counter(r["script"] for r in rows)))
    print("by department:", dict(Counter(r["department"] for r in rows)))
    print("by source:", dict(Counter(r["source"] for r in rows)))


if __name__ == "__main__":
    main()
