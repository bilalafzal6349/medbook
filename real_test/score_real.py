"""Score the baseline and the final XLM-R model on real, human-written messages.

    python score_real.py real_messages.csv                 # both engines -> ../results/real_v1/
    python score_real.py real_messages.csv --engines xlmr
    python score_real.py real_messages.csv --e2e           # also simulated booking chats opened by real messages
    python score_real.py real_messages.csv --check         # validate labels only

Input: the sheet from real_messages_template.csv (see LABELLING_GUIDE.md), a .txt file in the
data_gen/freeform_test.txt format, or a .jsonl file in the dataset format.

Two scores per engine, same metrics and layout as results/xlmr_v1/scores.json:
    real                 the model alone (intent head, department head, slot tags)
    real_with_backstop   what the running chatbot does: emergency keywords override the intent, phone and
                         booking-number regexes add missing slots, and the department is decided the way the
                         dialogue manager decides it (named doctor > named department > keyword/age router > model)
"""
import argparse
import csv
import json
import random
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for sub in ("backend", "models", "data_gen"):
    sys.path.insert(0, str(ROOT / sub))

from generate import script_of, tokens_and_tags  # noqa: E402
from schema import DEPARTMENTS, INTENTS, NO_DEPARTMENT, SLOTS  # noqa: E402

MARK_RE = re.compile(r"\[([^\]]+)\]\(([A-Z_]+)\)")
TOKEN_RE = re.compile(r"\w+(?:[-:]\w+)*|[^\w\s]")
BOOKING_INTENTS = {"book_appointment", "describe_symptom"}


# ----------------------------------------------------------------------------- loading + validation

def unmark(marked):
    text, spans, pos = "", [], 0
    for m in MARK_RE.finditer(marked):
        text += marked[pos:m.start()]
        spans.append((len(text), len(text) + len(m.group(1)), m.group(2)))
        text += m.group(1)
        pos = m.end()
    return text + marked[pos:], spans


def make_row(rid, text, spans, intent, dept, extra, problems, where):
    if intent not in INTENTS:
        problems.append(f"{where}: unknown intent '{intent}'")
    if dept not in DEPARTMENTS + [NO_DEPARTMENT]:
        problems.append(f"{where}: unknown department '{dept}'")
    for s, e, lab in spans:
        if lab not in SLOTS:
            problems.append(f"{where}: unknown slot '{lab}'")
        for m in TOKEN_RE.finditer(text):    # a slot must start and end on word edges
            if m.start() < s < m.end() or m.start() < e < m.end():
                problems.append(f"{where}: slot [{text[s:e]}]({lab}) cuts a word ('{m.group()}')")
                break
    tokens, tags = tokens_and_tags(text, spans)
    return {"id": rid, "text": text, "tokens": tokens, "tags": tags,
            "spans": [{"start": s, "end": e, "label": l, "value": text[s:e]} for s, e, l in spans],
            "intent": intent, "department": dept, "script": script_of(text), "style": script_of(text),
            "source": "human", "template_id": None, **extra}


def load_rows(path):
    path = Path(path)
    problems, rows, skipped = [], [], 0
    if path.suffix == ".jsonl":
        rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
        return rows, problems, skipped
    if path.suffix == ".txt":
        for n, line in enumerate(open(path, encoding="utf-8"), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            intent, dept, marked = [x.strip() for x in line.split("|", 2)]
            text, spans = unmark(marked)
            rows.append(make_row(f"r{len(rows):04d}", text, spans, intent, dept, {}, problems, f"line {n}"))
        return rows, problems, skipped
    with open(path, encoding="utf-8-sig", newline="") as f:
        for n, r in enumerate(csv.DictReader(f), 2):            # line 1 is the header
            r = {k.strip(): (v or "").strip() for k, v in r.items() if k}
            if not r.get("text") and not r.get("labelled_text"):
                continue
            if r.get("exclude", "") in ("1", "yes", "y", "true", "x"):
                skipped += 1
                continue
            where = f"line {n}"
            if not r.get("intent"):
                problems.append(f"{where}: no intent (row not labelled yet?)")
                continue
            raw = r.get("text") or ""
            text, spans = unmark(r.get("labelled_text") or raw)
            if raw and " ".join(text.split()) != " ".join(raw.split()):
                problems.append(f"{where}: labelled_text without brackets differs from text\n"
                                f"      text:     {raw}\n      labelled: {text}")
            extra = {"participant": r.get("participant", ""), "scenario": r.get("scenario", ""),
                     "reported_style": r.get("reported_style", "").lower()}
            rows.append(make_row(r.get("id") or f"r{len(rows):04d}", text, spans, r["intent"],
                                 r.get("department") or NO_DEPARTMENT, extra, problems, where))
    return rows, problems, skipped


# ----------------------------------------------------------------------------- metrics (as models/baseline.py)

def entities(tags):
    ents, cur = set(), None
    for i, t in enumerate(tags + ["O"]):
        if t.startswith("B-") or t == "O" or (t.startswith("I-") and (not cur or cur[0] != t[2:])):
            if cur:
                ents.add((cur[0], cur[1], i))
            cur = (t[2:], i) if t != "O" else None
    return ents


def entity_f1(gold, pred):
    tp = fp = fn = 0
    for g, p in zip(gold, pred):
        ge, pe = entities(g), entities(p)
        tp, fp, fn = tp + len(ge & pe), fp + len(pe - ge), fn + len(ge - pe)
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    return 2 * pr * rc / (pr + rc) if pr + rc else 0.0


def scores(rows, preds):
    from sklearn.metrics import accuracy_score, f1_score
    if not rows:
        return {"n": 0}
    routed = [i for i, r in enumerate(rows) if r["department"] != NO_DEPARTMENT]
    gi, pi = [r["intent"] for r in rows], [p["intent"] for p in preds]
    return {
        "n": len(rows),
        "intent_acc": round(accuracy_score(gi, pi), 4),
        "intent_macro_f1": round(f1_score(gi, pi, average="macro", zero_division=0), 4),
        "dept_top1_acc": round(sum(preds[i]["dept"] == rows[i]["department"] for i in routed) / len(routed), 4)
        if routed else None,
        "slot_entity_f1": round(entity_f1([r["tags"] for r in rows], [p["tags"] for p in preds]), 4),
    }


def breakdown(rows, preds, key):
    out = {"overall": scores(rows, preds)}
    groups = defaultdict(list)
    for i, r in enumerate(rows):
        if r.get(key):
            groups[r[key]].append(i)
    for g, idx in sorted(groups.items()):
        out[g] = scores([rows[i] for i in idx], [preds[i] for i in idx])
    return out


# ----------------------------------------------------------------------------- engines

def load_engine(name, model_dir):
    import nlu
    return nlu.BaselineEngine() if name == "baseline" else nlu.XLMREngine(model_dir)


def predict_model(engine, rows):
    """Raw model output per row: intent, department head (whatever the intent), slot tags."""
    out = []
    if engine.name == "baseline":
        from baseline import tok_features
        texts = [r["text"] for r in rows]
        ip, dp = engine.intent_m.predict_proba(texts), engine.dept_m.predict_proba(texts)
        tags = engine.crf.predict([[tok_features(r["tokens"], i) for i in range(len(r["tokens"]))] for r in rows])
        for a, b, t in zip(ip, dp, tags):
            out.append({"intent": str(engine.intent_m.classes_[a.argmax()]), "intent_conf": round(float(a.max()), 3),
                        "dept": str(engine.dept_m.classes_[b.argmax()]), "dept_conf": round(float(b.max()), 3),
                        "tags": list(t)})
        return out
    import torch
    from train_xlmr import NONE_DEPT_ID, fix_bio
    p = engine.parser
    for r in rows:
        enc = p.tok([r["tokens"]], is_split_into_words=True, truncation=True, max_length=p.labels["max_len"],
                    return_tensors="pt")
        with torch.no_grad():
            il, dl, sl = p.model(enc["input_ids"].to(p.device), enc["attention_mask"].to(p.device))
        ipr = il.softmax(-1)[0]
        dl = dl.clone()
        dl[:, NONE_DEPT_ID] = -1e9
        dpr = dl.softmax(-1)[0]
        first, prev = [], None
        for pos, w in enumerate(enc.word_ids(0)):
            if w is not None and w != prev:
                first.append(pos)
            prev = w
        sarg = sl.argmax(-1)[0].tolist()
        tags = fix_bio([p.labels["tags"][str(sarg[q])] for q in first] + ["O"] * (len(r["tokens"]) - len(first)))
        out.append({"intent": p.labels["intents"][str(int(ipr.argmax()))], "intent_conf": round(float(ipr.max()), 3),
                    "dept": p.labels["departments"][str(int(dpr.argmax()))], "dept_conf": round(float(dpr.max()), 3),
                    "tags": tags})
    return out


def with_backstop(rows, preds, clinic, matcher):
    """Apply the backend's rule layer and department router to the model output."""
    from dialogue import department_from_name
    from nlu import PHONE_RE, REF_RE, emergency_hit
    from routing import route
    out = []
    for r, p in zip(rows, preds):
        q = dict(p, tags=list(p["tags"]), dept_source="model")
        if emergency_hit(r["text"]):
            q["intent"] = "emergency"
        have = {lab for lab, _, _ in entities(q["tags"])}
        toks = [(m.start(), m.end()) for m in TOKEN_RE.finditer(r["text"])]
        for rx, lab in ((PHONE_RE, "PHONE"), (REF_RE, "APPOINTMENT_ID")):
            if lab in have:
                continue
            for m in rx.finditer(r["text"]):
                inside = [i for i, (s, e) in enumerate(toks) if s >= m.start() and e <= m.end()]
                for k, i in enumerate(inside):
                    q["tags"][i] = ("B-" if k == 0 else "I-") + lab
        did = matcher.find(r["text"])
        dslot = next((" ".join(r["tokens"][s:e]) for lab, s, e in sorted(entities(q["tags"]), key=lambda x: x[1])
                      if lab == "DEPARTMENT"), None)
        if did:
            q["dept"], q["dept_source"] = clinic.doctor(did)["department"], "doctor name"
        elif dslot and department_from_name(dslot):
            q["dept"], q["dept_source"] = department_from_name(dslot), "department name"
        else:
            q["dept"], q["dept_source"], _ = route(r["text"], p["dept"], p["dept_conf"])
        out.append(q)
    return out


def emergency_stats(rows, preds):
    emg = [p["intent"] == "emergency" for r, p in zip(rows, preds) if r["intent"] == "emergency"]
    oth = [p["intent"] == "emergency" for r, p in zip(rows, preds) if r["intent"] != "emergency"]
    return {"emergency_msgs": len(emg), "recall": round(sum(emg) / len(emg), 3) if emg else None,
            "other_msgs": len(oth), "false_alarm_rate": round(sum(oth) / len(oth), 3) if oth else None}


# ----------------------------------------------------------------------------- end to end

class FixedOpener:
    """Makes simulate.run_one open the chat with one given real message."""

    def __init__(self, row):
        self.row = row

    def get(self, *a, **k):
        return self.row


def end_to_end(engine, rows, seed):
    import simulate
    from clinic_db import Clinic
    from nlu import NLU
    data = ROOT / "data" / "dataset_v1"
    pool = simulate.Pool(simulate.load(data / "test.jsonl"),
                         backup=[simulate.Pool(simulate.load(data / "val.jsonl")),
                                 simulate.Pool(simulate.load(data / "train.jsonl"))])
    bot_nlu = NLU(Clinic(Path(tempfile.mkdtemp()) / "x.db").doctors(), engine=engine)
    rng = random.Random(seed)
    openers = [r for r in rows if r["intent"] in BOOKING_INTENTS and r["department"] != NO_DEPARTMENT]
    res = []
    for r in openers:
        out = simulate.run_one(rng, bot_nlu, pool, FixedOpener(r), "book", r["script"])
        res.append({"id": r["id"], "text": r["text"], **{k: out[k] for k in ("script", "ok", "turns", "gold_dept")},
                    "log": out["log"]})

    def summ(xs):
        return {"n": len(xs), "success": round(sum(x["ok"] for x in xs) / len(xs), 3) if xs else None,
                "avg_turns": round(sum(x["turns"] for x in xs) / len(xs), 1) if xs else None}
    return {"engine": engine.name, "openers": "real booking messages", "overall": summ(res),
            "by_script": {s: summ([x for x in res if x["script"] == s]) for s in ("roman", "urdu", "mixed")},
            "failures": [x for x in res if not x["ok"]]}


# ----------------------------------------------------------------------------- main

def table(title, res):
    lines = [f"**{title}**", "", "| split | n | intent acc | intent F1 | dept acc | slot F1 |", "|---|---|---|---|---|---|"]
    for k, v in res.items():
        if v.get("n"):
            lines.append(f"| {k} | {v['n']} | {v['intent_acc']} | {v['intent_macro_f1']} | "
                         f"{v['dept_top1_acc'] if v['dept_top1_acc'] is not None else '-'} | {v['slot_entity_f1']} |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", help="labelled .csv (template), .txt (freeform format) or .jsonl")
    ap.add_argument("--engines", default="baseline,xlmr")
    ap.add_argument("--model_dir", default=str(ROOT / "results" / "xlmr_final" / "model"))
    ap.add_argument("--out", default=str(ROOT / "results" / "real_v1"))
    ap.add_argument("--e2e", action="store_true", help="also run simulated booking chats opened by real messages")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--check", action="store_true", help="validate labels and stop")
    a = ap.parse_args()

    rows, problems, skipped = load_rows(a.file)
    print(f"{len(rows)} rows ({skipped} excluded) | intents {dict(Counter(r['intent'] for r in rows))}")
    print(f"scripts {dict(Counter(r['script'] for r in rows))} | "
          f"people {len({r['participant'] for r in rows if r.get('participant')})}")
    if problems:
        print(f"\n{len(problems)} labelling problem(s):\n  " + "\n  ".join(problems))
        if any("differs" in p or "unknown" in p for p in problems):
            sys.exit("fix the problems above first (or mark the rows exclude=1)")
    if a.check or not rows:
        return

    from clinic_db import Clinic
    from nlu import DoctorMatcher
    clinic = Clinic(Path(tempfile.mkdtemp()) / "s.db")
    matcher = DoctorMatcher(clinic.doctors())
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "test_real.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")
    summary = [f"# Real-message scores\n\nSource: `{Path(a.file).name}`, {len(rows)} messages, "
               f"{len({r['participant'] for r in rows if r.get('participant')}) or '?'} people.\n"]
    for name in [e.strip() for e in a.engines.split(",") if e.strip()]:
        engine = load_engine(name, a.model_dir)
        model = predict_model(engine, rows)
        full = with_backstop(rows, model, clinic, matcher)
        res = {"config": {"file": str(a.file), "engine": engine.name,
                          "model_dir": a.model_dir if engine.name == "xlmr" else None},
               "n_people": len({r["participant"] for r in rows if r.get("participant")}),
               "real": breakdown(rows, model, "script"),
               "real_with_backstop": breakdown(rows, full, "script"),
               "real_by_reported_style": breakdown(rows, full, "reported_style"),
               "emergency": {"model": emergency_stats(rows, model), "with_backstop": emergency_stats(rows, full)},
               "dept_decided_by": dict(Counter(q["dept_source"] for r, q in zip(rows, full)
                                               if r["department"] != NO_DEPARTMENT))}
        if a.e2e:
            e2e = end_to_end(engine, rows, a.seed)
            (out / f"e2e_{engine.name}.json").write_text(json.dumps(e2e, indent=2, ensure_ascii=False), "utf-8")
            res["e2e_booking"] = {k: e2e[k] for k in ("overall", "by_script")}
        (out / f"scores_{engine.name}.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), "utf-8")
        with open(out / f"errors_{engine.name}.jsonl", "w", encoding="utf-8") as f:
            for r, m, q in zip(rows, model, full):
                gold_ents = sorted(entities(r["tags"]))
                bad = [k for k, ok in (("intent", m["intent"] == r["intent"]),
                                       ("dept", r["department"] == NO_DEPARTMENT or m["dept"] == r["department"]),
                                       ("slots", sorted(entities(m["tags"])) == gold_ents)) if not ok]
                if bad:
                    def ents(t):
                        return [f"{lab}:{' '.join(r['tokens'][s:e])}" for lab, s, e in sorted(entities(t), key=lambda x: x[1])]
                    f.write(json.dumps({"id": r["id"], "script": r["script"], "text": r["text"], "wrong": bad,
                                        "gold_intent": r["intent"], "model_intent": m["intent"],
                                        "gold_dept": r["department"], "model_dept": m["dept"],
                                        "backstop_dept": q["dept"], "gold_slots": ents(r["tags"]),
                                        "model_slots": ents(m["tags"])}, ensure_ascii=False) + "\n")
        summary += [f"## {engine.name}\n", table("Model alone", res["real"]),
                    table("Model + backstop (the running chatbot)", res["real_with_backstop"]),
                    f"Emergency recall: model {res['emergency']['model']['recall']}, "
                    f"with backstop {res['emergency']['with_backstop']['recall']} "
                    f"({res['emergency']['model']['emergency_msgs']} emergency messages).\n"]
        if a.e2e:
            summary.append(f"End-to-end booking success: {res['e2e_booking']['overall']['success']} "
                           f"({res['e2e_booking']['overall']['n']} chats).\n")
        print("\n" + "\n".join(summary[-4:]))
    (out / "summary.md").write_text("\n".join(summary), "utf-8")
    print(f"written to {out}")


if __name__ == "__main__":
    main()
