"""NLU for the chatbot: the trained joint XLM-R model, or the TF-IDF/CRF baseline as a fallback,
plus a small rule layer that never depends on the model.

Every engine returns the same dict as models/predict_xlmr.py:

    {"text", "intent", "intent_conf", "slots": [{"label", "value"}],
     "department", "department_conf"}          # department only for routing intents

Engine choice (first that works):
    1. MEDBOOK_NLU=baseline forces the baseline.
    2. XLM-R weights: MEDBOOK_MODEL_DIR, else the newest results/*/model with joint_xlmr.pt
       or joint_xlmr_fp16.pt.part* files.
    3. Baseline, trained from data/dataset_v2 on first start (about 1 minute) and cached.

The rule layer adds what a model should not be trusted with alone:
    - emergency keywords (safety: a missed emergency is the worst error the bot can make)
    - phone numbers and MB-xxxx booking numbers (regular formats, regex is exact)
    - doctor names from the clinic database (fuzzy match on surname / first name)
"""
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "data_gen"))
sys.path.insert(0, str(ROOT / "models"))

ROUTING_INTENTS = {"book_appointment", "describe_symptom", "doctor_availability"}
TOKEN_RE = re.compile(r"\w+(?:[-:]\w+)*|[^\w\s]")   # same as data_gen/generate.py


def simple_tokenize(text):
    return TOKEN_RE.findall(text)


# ----------------------------------------------------------------------------- engines

WEIGHT_GLOBS = ("joint_xlmr.pt", "joint_xlmr_fp16.pt.part*")   # fp32 file, or fp16 split into parts


def _has_weights(d):
    return any(any(Path(d).glob(g)) for g in WEIGHT_GLOBS)


def find_xlmr_dir():
    """MEDBOOK_MODEL_DIR, else the most recently written results/*/model with weights.
    predict_xlmr.load_weights joins fp16 parts and casts them back to fp32."""
    env = os.environ.get("MEDBOOK_MODEL_DIR")
    if env:
        return Path(env) if _has_weights(env) else None
    dirs = [d for d in (ROOT / "results").glob("*/model") if _has_weights(d)]
    if not dirs:
        return None
    return max(dirs, key=lambda d: max(f.stat().st_mtime for g in WEIGHT_GLOBS for f in d.glob(g)))


class XLMREngine:
    name = "xlmr"

    def __init__(self, model_dir):
        from predict_xlmr import Parser   # imports torch + transformers
        self.parser = Parser(model_dir)
        self.model_dir = str(model_dir)

    def __call__(self, text):
        return self.parser(text)

    def department_only(self, text):
        """Department head output whatever the intent (Parser only reports it for routing intents)."""
        import torch
        from train_xlmr import NONE_DEPT_ID
        p = self.parser
        words = simple_tokenize(text)
        enc = p.tok([words], is_split_into_words=True, truncation=True, max_length=p.labels["max_len"],
                    return_tensors="pt")
        with torch.no_grad():
            _, dl, _ = p.model(enc["input_ids"].to(p.device), enc["attention_mask"].to(p.device))
        dl = dl.clone()
        dl[:, NONE_DEPT_ID] = -1e9
        dp = dl.softmax(-1)[0]
        return p.labels["departments"][str(int(dp.argmax()))], round(float(dp.max()), 3)


class BaselineEngine:
    """TF-IDF + logistic regression (intent, department) and CRF (slots), as in models/baseline.py."""
    name = "baseline"

    def __init__(self, data_dir=ROOT / "data" / "dataset_v2", cache=HERE / ".cache" / "baseline_v2.joblib"):
        import joblib
        if cache.exists():
            self.intent_m, self.dept_m, self.crf = joblib.load(cache)
            return
        from baseline import load, text_clf, tok_features
        import sklearn_crfsuite
        t0 = time.time()
        print("[nlu] training baseline from", data_dir, "(first start only)...", flush=True)
        train = load(Path(data_dir) / "train.jsonl") + load(Path(data_dir) / "val.jsonl")
        self.intent_m = text_clf().fit([r["text"] for r in train], [r["intent"] for r in train])
        dtrain = [r for r in train if r["department"] != "none"]
        self.dept_m = text_clf().fit([r["text"] for r in dtrain], [r["department"] for r in dtrain])
        self.crf = sklearn_crfsuite.CRF(algorithm="lbfgs", c1=0.1, c2=0.1, max_iterations=150)
        self.crf.fit([[tok_features(r["tokens"], i) for i in range(len(r["tokens"]))] for r in train],
                     [r["tags"] for r in train])
        cache.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump((self.intent_m, self.dept_m, self.crf), cache)
        print(f"[nlu] baseline ready in {time.time() - t0:.0f}s, cached at {cache}", flush=True)

    def __call__(self, text):
        from baseline import entities, tok_features
        words = simple_tokenize(text)
        ip = self.intent_m.predict_proba([text])[0]
        k = ip.argmax()
        intent = self.intent_m.classes_[k]
        tags = self.crf.predict_single([tok_features(words, i) for i in range(len(words))]) if words else []
        out = {"text": text, "intent": str(intent), "intent_conf": round(float(ip[k]), 3),
               "slots": [{"label": lab, "value": " ".join(words[s:e])}
                         for lab, s, e in sorted(entities(list(tags)), key=lambda x: x[1])]}
        if intent in ROUTING_INTENTS:
            dp = self.dept_m.predict_proba([text])[0]
            j = dp.argmax()
            out["department"] = str(self.dept_m.classes_[j])
            out["department_conf"] = round(float(dp[j]), 3)
        return out

    def department_only(self, text):
        dp = self.dept_m.predict_proba([text])[0]
        j = dp.argmax()
        return str(self.dept_m.classes_[j]), round(float(dp[j]), 3)


def load_engine():
    if os.environ.get("MEDBOOK_NLU", "").lower() != "baseline":
        d = find_xlmr_dir()
        if d:
            try:
                e = XLMREngine(d)
                print(f"[nlu] using XLM-R from {d}", flush=True)
                return e
            except Exception as ex:   # missing torch, bad checkpoint, ...
                print(f"[nlu] XLM-R not usable ({ex!r}); falling back to baseline", flush=True)
        else:
            print("[nlu] no XLM-R weights found; using baseline", flush=True)
    return BaselineEngine()


# ----------------------------------------------------------------------------- rules

EMERGENCY_PATTERNS = [
    # roman urdu / english
    r"behosh|be hosh|hosh nahi|unconscious|faint ho",
    r"saans (bilkul )?nahi aa (rahi|raha)|saans nahi le|can'?t breathe|not breathing|saans ruk",
    r"khoon (bohat|bahut|bht)? ?(beh|bah|nikal)|khoon (nahi|nhi) ruk|bleeding (a lot|heavily|badly)|heavy bleeding",
    r"heart attack|dil ka daura|dil ka dora|cardiac arrest",
    r"stroke|falij|faalij|munh (terha|tedha|tehra)",
    r"zeher|zehar|poison",
    r"current lag|bijli ka jhatka|electric shock",
    r"(buri tarah|bohat|bahut) jal gay|burn(ed|t) badly",
    r"(dora|daura|dore) (par|parr|pad) (raha|rahe|gaya)|fits? (aa|par) rah|seizure|mirgi",
    r"accident|haadsa|hadsa",
    r"seene mein (shadeed|bohat tez|bahut tez|bht tez) dard|severe chest pain",
    r"goliyan kha li|overdose|khud ?kushi|suicide|marna chahta|marna chahti",
    r"sar phat|sir phat",
    # urdu script
    r"بے ہوش|ہوش نہیں",
    r"سانس (بالکل )?نہیں آ (رہی|رہا)|سانس رک",
    r"خون (بہت )?(بہہ|بہ) رہا|خون (نہیں )?رک (نہیں )?رہا",
    r"دل کا دورہ|ہارٹ اٹیک",
    r"فالج|منہ ٹیڑھا",
    r"زہر",
    r"کرنٹ لگ",
    r"بری طرح جل",
    r"دورہ پڑ",
    r"ایکسیڈنٹ|حادثہ",
    r"سینے میں شدید درد",
    r"خودکشی|گولیاں کھا لی",
]
EMERGENCY_RE = re.compile("|".join(f"(?:{p})" for p in EMERGENCY_PATTERNS), re.IGNORECASE)

PHONE_RE = re.compile(r"(?:\+92|0092|0)[\s-]?3\d{2}[\s-]?\d{7}|(?:\+92|0)[\s-]?3\d{2}[\s-]?\d{3}[\s-]?\d{4}"
                      r"|[۰۳][۰-۹\s-]{10,13}")
REF_RE = re.compile(r"\bmb[\s-]?\d{3,5}\b", re.IGNORECASE)
AGE_RE = re.compile(r"\b(\d{1,3})\s*(saal|sal|years?|yrs?|mahine|months?)\b|(\d{1,3})\s*(سال|مہینے)", re.IGNORECASE)


def emergency_hit(text):
    m = EMERGENCY_RE.search(text)
    return m.group(0) if m else None


def rule_slots(text):
    out = []
    for m in PHONE_RE.finditer(text):
        out.append({"label": "PHONE", "value": m.group(0).strip()})
    for m in REF_RE.finditer(text):
        out.append({"label": "APPOINTMENT_ID", "value": m.group(0)})
    return out


def restore_spans(text, slots):
    """Engines return slot values as space-joined tokens ('Dr . Ayesha'); give back the original text."""
    toks = [(m.group(0), m.start(), m.end()) for m in TOKEN_RE.finditer(text)]
    words = [t[0] for t in toks]
    used = set()
    out = []
    for s in slots:
        parts = s["value"].split(" ")
        n = len(parts)
        for i in range(len(words) - n + 1):
            if words[i:i + n] == parts and i not in used:
                used.add(i)
                s = dict(s, value=text[toks[i][1]:toks[i + n - 1][2]])
                break
        out.append(s)
    return out


class DoctorMatcher:
    """Find a clinic doctor mentioned in text: full name, 'Dr Kamran', 'Kamran Shah sahab', Urdu script."""

    def __init__(self, doctors):
        self.keys = []   # (pattern, doctor_id, strength)
        first_counts = {}
        for d in doctors:
            first = d["name_roman"].replace("Dr. ", "").split()[0].lower()
            first_counts[first] = first_counts.get(first, 0) + 1
        for d in doctors:
            parts = d["name_roman"].replace("Dr. ", "").split()
            full = " ".join(parts).lower()
            self.keys.append((re.compile(rf"\b{re.escape(full)}\b", re.I), d["id"], 3))
            urdu = d["name_urdu"].replace("ڈاکٹر ", "")
            self.keys.append((re.compile(re.escape(urdu)), d["id"], 3))
            # "Dr Kamran", "doctor Kamran", "ڈاکٹر کامران" (first name only, unique first names)
            if first_counts[parts[0].lower()] == 1:
                self.keys.append((re.compile(rf"\b(dr\.?|doctor|daktar)\s+{re.escape(parts[0])}\b", re.I), d["id"], 2))
                self.keys.append((re.compile(rf"ڈاکٹر\s+{re.escape(urdu.split()[0])}"), d["id"], 2))
            self.keys.append((re.compile(rf"\b(dr\.?|doctor)\s+{re.escape(parts[-1])}\b", re.I), d["id"], 1))

    def find(self, text):
        best = None
        for pat, did, strength in self.keys:
            if pat.search(text) and (best is None or strength > best[1]):
                best = (did, strength)
        return best[0] if best else None


class NLU:
    """Model + rules. `parse` returns the model dict plus 'rules' (what the rules added or overrode)."""

    def __init__(self, doctors, engine=None):
        self.engine = engine or load_engine()
        self.doctors = DoctorMatcher(doctors)
        self._dept_backup = None

    @property
    def engine_name(self):
        return self.engine.name

    def parse(self, text):
        t0 = time.time()
        out = self.engine(text)
        out["slots"] = restore_spans(text, out["slots"])
        rules = {}
        hit = emergency_hit(text)
        if hit:
            rules["emergency"] = hit
            if out["intent"] != "emergency":
                rules["intent_override"] = f"{out['intent']} -> emergency"
                out["intent"] = "emergency"
        labels = {s["label"] for s in out["slots"]}
        for s in rule_slots(text):
            if s["label"] not in labels:
                out["slots"].append(s)
                rules.setdefault("added_slots", []).append(s["label"])
            else:   # model found one; trust the exact regex value
                for ms in out["slots"]:
                    if ms["label"] == s["label"]:
                        ms["value"] = s["value"]
        did = self.doctors.find(text)
        if did:
            rules["doctor_id"] = did
        out["rules"] = rules
        out["engine"] = self.engine.name
        out["ms"] = round((time.time() - t0) * 1000)
        return out

    def department_of(self, text):
        """Department guess for a text whatever its intent (used when the user answers 'which department?')."""
        if hasattr(self.engine, "department_only"):
            return self.engine.department_only(text)
        r = self.engine(text)
        return r.get("department"), r.get("department_conf", 0.0)
