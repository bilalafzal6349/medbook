"""Build the full MedBook dataset (v2: age-aware pediatrics labels) in one go.

Usage:
    python build_dataset.py --out ../data/dataset_v2

Writes:
    train.jsonl / val.jsonl / test.jsonl   template-generated rows, split by template
    test_freeform.jsonl                    hand-written rows (not from templates), test only
    dialogues.jsonl                        multi-turn dialogues for end-to-end testing
    stats.json, samples.md
"""
import argparse
import json
import random
import re
from collections import Counter
from pathlib import Path

from generate import (PLACEHOLDER_RE, fill, generate, script_of, split_templates, tokens_and_tags, wrap)
from schema import DEPARTMENTS, INTENTS, NO_DEPARTMENT, SLOTS
from templates import TEMPLATES

MARK_RE = re.compile(r"\[([^\]]+)\]\(([A-Z_]+)\)")


# ------------------------------------------------------------------ free-form test set
def parse_freeform(path):
    rows = []
    for n, line in enumerate(open(path, encoding="utf-8")):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        intent, dept, marked = [x.strip() for x in line.split("|", 2)]
        assert intent in INTENTS, (n, intent)
        assert dept in DEPARTMENTS + [NO_DEPARTMENT], (n, dept)
        text, spans, pos = "", [], 0
        for m in MARK_RE.finditer(marked):
            text += marked[pos:m.start()]
            assert m.group(2) in SLOTS, (n, m.group(2))
            spans.append((len(text), len(text) + len(m.group(1)), m.group(2)))
            text += m.group(1)
            pos = m.end()
        text += marked[pos:]
        tokens, tags = tokens_and_tags(text, spans)
        rows.append({
            "id": f"ff-{len(rows):04d}", "text": text, "tokens": tokens, "tags": tags,
            "spans": [{"start": s, "end": e, "label": l, "value": text[s:e]} for s, e, l in spans],
            "intent": intent, "department": dept, "script": script_of(text), "style": script_of(text),
            "source": "freeform", "template_id": None,
        })
    return rows


# ------------------------------------------------------------------ dialogues
SYS = {
    "ask_DATE": {"roman": "Kis din ka appointment chahiye?", "urdu": "کس دن کا وقت چاہیے؟"},
    "ask_TIME": {"roman": "Kis waqt aana pasand karenge?", "urdu": "کس وقت آنا پسند کریں گے؟"},
    "ask_PATIENT_NAME": {"roman": "Patient ka naam bata dein.", "urdu": "مریض کا نام بتا دیں۔"},
    "ask_PHONE": {"roman": "Apna mobile number bata dein.", "urdu": "اپنا موبائل نمبر بتا دیں۔"},
    "ask_DEPARTMENT": {"roman": "Kis doctor ya department ko dikhana hai? Ya apni takleef bata dein.",
                       "urdu": "کس ڈاکٹر یا شعبے کو دکھانا ہے؟ یا اپنی تکلیف بتا دیں۔"},
    "ask_APPOINTMENT_ID": {"roman": "Apna booking number bata dein (MB-xxxx).",
                           "urdu": "اپنا بکنگ نمبر بتا دیں (MB-xxxx)۔"},
    "route": {"roman": "Aapki takleef ke hisaab se {dept} behtar rahega.",
              "urdu": "آپ کی تکلیف کے حساب سے {dept} بہتر رہے گا۔"},
    "confirm": {"roman": "{summary}. Confirm kar doon?", "urdu": "{summary}۔ کیا پکا کر دوں؟"},
    "done": {"roman": "Ho gaya! Aapka booking number {ref} hai.", "urdu": "ہو گیا! آپ کا بکنگ نمبر {ref} ہے۔"},
    "emergency": {"roman": "Ye emergency lagti hai. Foran 1122 par call karein ya qareebi emergency jayen.",
                  "urdu": "یہ ایمرجنسی لگتی ہے۔ فوراً 1122 پر کال کریں یا قریبی ایمرجنسی جائیں۔"},
    "bye": {"roman": "Allah hafiz, sehat ka khayal rakhein.", "urdu": "اللہ حافظ، صحت کا خیال رکھیں۔"},
}
REQUIRED = {
    "book_appointment": ["DEPARTMENT", "DATE", "TIME", "PATIENT_NAME", "PHONE"],
    "reschedule_appointment": ["APPOINTMENT_ID", "DATE", "TIME"],
    "cancel_appointment": ["APPOINTMENT_ID"],
    "check_appointment": ["APPOINTMENT_ID"],
}


def by_intent_style(intent, style, need=None, only=None):
    """Templates of an intent/style; need = slot that must appear; only = allowed slot set."""
    out = []
    for tid, i, s, text in TEMPLATES:
        if i != intent or s != style:
            continue
        slots = set(PLACEHOLDER_RE.findall(text)) - {"CHILD"}
        slots = {"SYMPTOM" if x == "CSYMPTOM" else x for x in slots}
        if need and need not in slots:
            continue
        if only is not None and not slots <= only:
            continue
        out.append((tid, text))
    return out


def user_turn(rng, intent, style, tpl):
    tid, text_t = tpl
    text, spans, dept = fill(rng, text_t, style)
    text, spans = wrap(rng, text, spans, style, intent)
    tokens, tags = tokens_and_tags(text, spans)
    return {"speaker": "user", "text": text, "tokens": tokens, "tags": tags, "intent": intent,
            "spans": [{"start": s, "end": e, "label": l, "value": text[s:e]} for s, e, l in spans],
            "department": dept or NO_DEPARTMENT, "template_id": tid, "script": script_of(text)}


def sys_turn(act, style, **kw):
    key = "urdu" if style == "urdu" else "roman"
    return {"speaker": "system", "act": act, "text": SYS[act][key].format(**kw)}


def make_dialogue(rng, idx):
    style = rng.choice(["roman", "roman", "urdu", "mixed"])
    sstyle = "urdu" if style == "urdu" else "roman"
    task = rng.choices(["book_appointment", "reschedule_appointment", "cancel_appointment",
                        "check_appointment", "emergency"], weights=[60, 15, 10, 10, 5])[0]
    turns, state = [], {}

    def add_user(intent, tpl):
        t = user_turn(rng, intent, style, tpl)
        for s in t["spans"]:
            state[s["label"]] = s["value"]  # later values overwrite (corrections)
        if t["department"] != NO_DEPARTMENT:
            state["_department"] = t["department"]
        t["state"] = dict(state)
        turns.append(t)
        return t

    if rng.random() < 0.4:
        add_user("greet", rng.choice(by_intent_style("greet", style)))
        turns.append({"speaker": "system", "act": "greet",
                      "text": "Walaikum salam! Main MedBook hoon, kaise madad karun?" if sstyle == "roman"
                      else "وعلیکم السلام! میں میڈبک ہوں، کیسے مدد کروں؟"})
    if task == "emergency":
        add_user("emergency", rng.choice(by_intent_style("emergency", style)))
        turns.append(sys_turn("emergency", style))
        return {"id": f"dlg-{idx:04d}", "task": task, "style": style, "turns": turns, "success": True}

    opener = rng.choice(by_intent_style(task, style))
    t = add_user(task, opener)
    if task == "book_appointment" and "SYMPTOM" in state and state.get("_department"):
        state.setdefault("DEPARTMENT", state["_department"])
        turns.append(sys_turn("route", style, dept=state["_department"].replace("_", " ")))
    if task == "book_appointment" and "DOCTOR" in state:
        state.setdefault("DEPARTMENT", state.get("_department", ""))

    for slot in REQUIRED[task]:
        if slot in state:
            continue
        turns.append(sys_turn(f"ask_{slot}", style))
        if slot == "DEPARTMENT" and rng.random() < 0.5:  # answer with a symptom instead
            tpl = rng.choice(by_intent_style("describe_symptom", style, need="SYMPTOM"))
            add_user("describe_symptom", tpl)
            state["DEPARTMENT"] = state.get("_department", "general_physician")
            turns.append(sys_turn("route", style, dept=state["DEPARTMENT"].replace("_", " ")))
            continue
        opts = by_intent_style("inform", style, need=slot, only={slot}) or \
            by_intent_style("inform", "roman", need=slot, only={slot})
        add_user("inform", rng.choice(opts))
        if slot == "DEPARTMENT":
            state["DEPARTMENT"] = state.get("_department", state.get("DEPARTMENT"))

    summary = ", ".join(f"{k}: {v}" for k, v in state.items() if not k.startswith("_"))
    turns.append(sys_turn("confirm", style, summary=summary))
    if rng.random() < 0.2 and task in ("book_appointment", "reschedule_appointment"):
        slot = rng.choice(["DATE", "TIME"])
        opts = by_intent_style("deny", style, need=slot, only={slot})
        if opts:
            add_user("deny", rng.choice(opts))
            summary = ", ".join(f"{k}: {v}" for k, v in state.items() if not k.startswith("_"))
            turns.append(sys_turn("confirm", style, summary=summary))
    add_user("confirm", rng.choice(by_intent_style("confirm", style)))
    turns.append(sys_turn("done", style, ref=f"MB-{rng.randint(1000, 9999)}"))
    if rng.random() < 0.6:
        add_user("goodbye", rng.choice(by_intent_style("goodbye", style)))
        turns.append(sys_turn("bye", style))
    final = {k: v for k, v in state.items() if not k.startswith("_")}
    return {"id": f"dlg-{idx:04d}", "task": task, "style": style, "goal": final,
            "department": state.get("_department", NO_DEPARTMENT), "turns": turns, "success": True}


# ------------------------------------------------------------------ main
def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="../data/dataset_v2")
    ap.add_argument("--per-template", type=int, default=30)
    ap.add_argument("--noise-frac", type=float, default=0.25)
    ap.add_argument("--dialogues", type=int, default=600)
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    rows = generate(args.per_template, args.seed, args.noise_frac)
    assign = split_templates(random.Random(args.seed))
    splits = {k: [r for r in rows if assign[r["template_id"]] == k] for k in ("train", "val", "test")}
    for k, v in splits.items():
        write_jsonl(out / f"{k}.jsonl", v)

    ff = parse_freeform(Path(__file__).with_name("freeform_test.txt"))
    write_jsonl(out / "test_freeform.jsonl", ff)

    rng = random.Random(args.seed + 1)
    dialogues = [make_dialogue(rng, i) for i in range(args.dialogues)]
    write_jsonl(out / "dialogues.jsonl", dialogues)

    # sanity checks
    for r in rows + ff:
        for s in r["spans"]:
            assert r["text"][s["start"]:s["end"]] == s["value"], r["id"]
        assert len(r["tokens"]) == len(r["tags"]), r["id"]
    train_texts = {r["text"] for r in splits["train"]}
    leak = sum(r["text"] in train_texts for r in splits["test"] + ff)

    def summary(rs):
        return {"rows": len(rs), "intent": dict(Counter(r["intent"] for r in rs)),
                "script": dict(Counter(r["script"] for r in rs)),
                "department": dict(Counter(r["department"] for r in rs)),
                "source": dict(Counter(r["source"] for r in rs)),
                "slots": dict(Counter(s["label"] for r in rs for s in r["spans"]))}

    stats = {k: summary(v) for k, v in splits.items()}
    stats["test_freeform"] = summary(ff)
    stats["dialogues"] = {"count": len(dialogues), "task": dict(Counter(d["task"] for d in dialogues)),
                          "style": dict(Counter(d["style"] for d in dialogues)),
                          "avg_turns": round(sum(len(d["turns"]) for d in dialogues) / len(dialogues), 1),
                          "user_turns": sum(1 for d in dialogues for t in d["turns"] if t["speaker"] == "user")}
    stats["templates"] = {"total": len(TEMPLATES), "by_split": dict(Counter(assign.values()))}
    stats["exact_text_overlap_test_vs_train"] = leak
    (out / "stats.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")

    # human-readable samples
    srng = random.Random(3)
    lines = ["# Dataset v2 samples", "", "| split | text | intent | department | script | slots |",
             "|---|---|---|---|---|---|"]
    for k in ("train", "test"):
        for r in srng.sample(splits[k], 15):
            sl = "; ".join(f"{s['label']}={s['value']}" for s in r["spans"]) or "-"
            lines.append(f"| {k} | {r['text']} | {r['intent']} | {r['department']} | {r['script']} | {sl} |")
    lines += ["", "## Example dialogue", ""]
    d = next(d for d in dialogues if d["task"] == "book_appointment" and len(d["turns"]) >= 10)
    for t in d["turns"]:
        tag = f" `[{t['intent']}]`" if t["speaker"] == "user" else f" `[{t['act']}]`"
        lines.append(f"- **{t['speaker']}:** {t['text']}{tag}")
    (out / "samples.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    for k in ("train", "val", "test", "test_freeform"):
        print(k, stats[k]["rows"], stats[k]["script"])
    print("dialogues", stats["dialogues"])
    print("templates:", stats["templates"], "| exact overlap test/train:", leak)


if __name__ == "__main__":
    main()
