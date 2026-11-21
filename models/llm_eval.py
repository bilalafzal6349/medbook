"""Evaluate an LLM as the NLU (intent + department + slots) on the same test sets as XLM-R.

The LLM gets one message at a time and must answer with JSON:
    {"intent": ..., "department": ..., "slots": [{"label": ..., "value": ...}]}
Slot values are mapped back onto the gold tokens, so slot F1 is computed exactly like
baseline.py / train_xlmr.py (entity-level, exact span match). A value that cannot be found
in the message counts as a false positive. A relaxed slot F1 (same label, overlapping tokens)
is also reported, because LLMs often pick slightly different span boundaries.

Backends (pick with --backend):
    anthropic   Claude API. Needs ANTHROPIC_API_KEY (pip install anthropic).
    openai      Any OpenAI-compatible server: Groq, OpenRouter, Together, Gemini's OpenAI
                endpoint, a local Ollama or vLLM. Needs OPENAI_API_KEY and, for anything but
                OpenAI itself, OPENAI_BASE_URL (pip install openai).
    llamacpp    A local GGUF model on CPU, no key at all (pip install llama-cpp-python).

Examples:
    # free, local, no key (download a GGUF first, see results/llm_compare/README.md)
    python llm_eval.py --backend llamacpp --model ~/llm/qwen2.5-3b-instruct-q4_k_m.gguf \
        --shots few --out ../results/llm_compare/qwen2.5-3b_few

    # Claude
    export ANTHROPIC_API_KEY=...
    python llm_eval.py --backend anthropic --model claude-haiku-5-5 --shots zero \
        --out ../results/llm_compare/claude-haiku-5-5_zero

    # Groq (free tier) through the OpenAI-compatible backend
    export OPENAI_API_KEY=... OPENAI_BASE_URL=https://api.groq.com/openai/v1
    python llm_eval.py --backend openai --model llama-3.3-70b-versatile --shots few \
        --price_in 0.59 --price_out 0.79 --out ../results/llm_compare/llama3.3-70b_few

Outputs in --out: predictions_<set>.jsonl (one line per message, raw reply, latency, tokens),
scores.json (overall and per script, plus latency and cost per message) and config.json.
Runs resume: messages already in predictions_<set>.jsonl are skipped, so a crash or a rate
limit costs nothing. Delete the file to start over.
"""
import argparse
import json
import os
import random
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "data_gen"))
from lexicons import DOCTORS  # noqa: E402
from schema import DEPARTMENTS, INTENTS, NO_DEPARTMENT, SLOTS  # noqa: E402

TOKEN_RE = re.compile(r"\w+(?:[-:]\w+)*|[^\w\s]")  # same as data_gen/generate.py

# USD per 1M tokens (input, output). Claude prices from Anthropic's price list (Nov 2026).
# Override with --price_in / --price_out for any other model.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}
CACHE_READ_FACTOR = 0.1  # Anthropic bills cached input at about 0.1x

DEPT_HINTS = {
    "general_physician": "fever, flu, cough, body ache, weakness, BP/sugar check, anything general",
    "cardiology": "heart, chest pain, palpitations, breathlessness on walking, high BP follow-up",
    "dermatology": "skin, rash, itching, acne, hair fall, spots, allergy on skin",
    "ent": "ear, nose, throat, tonsils, sinus, hearing, nose bleeding",
    "gastroenterology": "stomach, acidity, indigestion, vomiting, diarrhoea, liver",
    "orthopedics": "bones, joints, back pain, knee pain, fracture, sprain",
    "gynecology": "women's health, periods, pregnancy, lady doctor",
    "pediatrics": "any complaint of a baby or child, child specialist",
}


# ---------------------------------------------------------------- prompt

def doctor_directory():
    return "\n".join(f"- {n['roman']} / {n['urdu']}: {d}" for n, d in DOCTORS)


def system_prompt(fewshot_rows):
    intents = "\n".join(f"- {k}: {v}" for k, v in INTENTS.items())
    slots = "\n".join(f"- {k}: {v}" for k, v in SLOTS.items())
    depts = "\n".join(f"- {k}: {v}" for k, v in DEPT_HINTS.items())
    p = f"""You are the language-understanding module of MedBook, an appointment chatbot for a clinic in Pakistan.
Patients write in Roman Urdu, in Urdu script, or in Urdu script mixed with English words.
Read ONE patient message and return JSON with three fields.

1. "intent": exactly one of
{intents}

2. "department": the clinic department the message should be routed to, one of
{depts}
Use "{NO_DEPARTMENT}" when the message carries no medical or doctor signal at all (a name, a date, yes/no,
greetings, clinic timings). A named doctor implies that doctor's department:
{doctor_directory()}

3. "slots": every entity in the message, as {{"label": ..., "value": ...}} where label is one of
{slots}
"value" must be copied exactly as it is written in the message (same script, same spelling), and must be
the shortest phrase that names the entity: for a DOCTOR include the title (Dr., ڈاکٹر); for a SYMPTOM give the
complaint itself without "mujhe", "hai" or durations; for DATE and TIME give only the date or time words.
Return an empty list when there are no entities.

Answer with the JSON object only."""
    if fewshot_rows:
        ex = "\n".join(f"Message: {r['text']}\nJSON: {json.dumps(gold_json(r), ensure_ascii=False)}"
                       for r in fewshot_rows)
        p += f"\n\nExamples of correct answers:\n\n{ex}"
    return p


def gold_json(r):
    return {"intent": r["intent"], "department": r["department"],
            "slots": [{"label": s["label"], "value": s["value"]} for s in r["spans"]]}


def pick_fewshot(train_rows, per_intent=2, seed=13):
    """Two training rows per intent (different scripts where possible), plus one row per
    department that the intent rows did not already cover. Fixed seed, so every model sees
    the same examples and the prompt prefix can be cached."""
    rng = random.Random(seed)
    by_intent = defaultdict(list)
    for r in train_rows:
        if r["source"] == "template":
            by_intent[r["intent"]].append(r)
    picked = []
    for intent in INTENTS:
        rows = by_intent[intent][:]
        rng.shuffle(rows)
        seen_scripts = set()
        for r in rows:
            if r["script"] not in seen_scripts:
                picked.append(r)
                seen_scripts.add(r["script"])
            if len(seen_scripts) == per_intent:
                break
    covered = {r["department"] for r in picked}
    for d in DEPARTMENTS:
        if d not in covered:
            cands = [r for r in train_rows if r["department"] == d and r["intent"] == "describe_symptom"]
            picked.append(rng.choice(cands))
    rng.shuffle(picked)
    return picked


SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": list(INTENTS)},
        "department": {"type": "string", "enum": DEPARTMENTS + [NO_DEPARTMENT]},
        "slots": {"type": "array", "items": {
            "type": "object",
            "properties": {"label": {"type": "string", "enum": list(SLOTS)}, "value": {"type": "string"}},
            "required": ["label", "value"], "additionalProperties": False}},
    },
    "required": ["intent", "department", "slots"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------- backends
# Each returns (reply_text, usage dict with in / cached_in / out tokens).

class AnthropicBackend:
    def __init__(self, model, system):
        import anthropic
        self.client = anthropic.Anthropic()
        self.model, self.system = model, system

    def __call__(self, text):
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            # the long instructions + examples are identical for every message, so cache them
            system=[{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": text}],
        )
        if resp.stop_reason == "refusal":
            return "", {"in": resp.usage.input_tokens, "cached_in": 0, "out": resp.usage.output_tokens}
        reply = next((b.text for b in resp.content if b.type == "text"), "")
        u = resp.usage
        return reply, {"in": u.input_tokens + (u.cache_creation_input_tokens or 0),
                       "cached_in": u.cache_read_input_tokens or 0, "out": u.output_tokens}


class OpenAIBackend:
    def __init__(self, model, system, json_mode="schema"):
        import openai
        self.client = openai.OpenAI()  # reads OPENAI_API_KEY and OPENAI_BASE_URL
        self.model, self.system, self.json_mode = model, system, json_mode

    def __call__(self, text):
        fmt = ({"type": "json_schema", "json_schema": {"name": "nlu", "schema": SCHEMA, "strict": True}}
               if self.json_mode == "schema" else {"type": "json_object"})
        resp = self.client.chat.completions.create(
            model=self.model, temperature=0, max_tokens=400, response_format=fmt,
            messages=[{"role": "system", "content": self.system}, {"role": "user", "content": text}])
        u = resp.usage
        cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
        return resp.choices[0].message.content or "", {"in": u.prompt_tokens - cached, "cached_in": cached,
                                                       "out": u.completion_tokens}


class LlamaCppBackend:
    def __init__(self, model, system, n_ctx=8192, threads=None):
        from llama_cpp import Llama
        self.llm = Llama(model_path=os.path.expanduser(model), n_ctx=n_ctx, n_threads=threads or os.cpu_count(),
                         verbose=False, seed=13)
        self.system = system

    def __call__(self, text):
        # llama.cpp keeps the KV cache of the previous prompt and reuses the shared prefix
        # (the system prompt), so only the new message is processed after the first call.
        resp = self.llm.create_chat_completion(
            messages=[{"role": "system", "content": self.system}, {"role": "user", "content": text}],
            temperature=0, max_tokens=300,
            response_format={"type": "json_object", "schema": SCHEMA})  # grammar-constrained
        u = resp["usage"]
        return resp["choices"][0]["message"]["content"] or "", {"in": u["prompt_tokens"], "cached_in": 0,
                                                                "out": u["completion_tokens"]}


# ---------------------------------------------------------------- scoring

def entities(tags):
    ents, cur = set(), None
    for i, t in enumerate(tags + ["O"]):
        if t.startswith("B-") or t == "O" or (t.startswith("I-") and (not cur or cur[0] != t[2:])):
            if cur:
                ents.add((cur[0], cur[1], i))
            cur = (t[2:], i) if t != "O" else None
    return ents


def norm(w):
    return w.lower()


def locate(tokens, value, used):
    """Token span (start, end) of value inside tokens, or None. Prefers an unused occurrence."""
    vt = [norm(w) for w in TOKEN_RE.findall(value)]
    if not vt:
        return None
    toks = [norm(w) for w in tokens]
    hits = [i for i in range(len(toks) - len(vt) + 1) if toks[i:i + len(vt)] == vt]
    for i in hits:
        if (i, i + len(vt)) not in used:
            return i, i + len(vt)
    return (hits[0], hits[0] + len(vt)) if hits else None


def parse_reply(reply):
    try:
        d = json.loads(reply)
    except (json.JSONDecodeError, TypeError):
        m = re.search(r"\{.*\}", reply or "", re.S)
        try:
            d = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            d = {}
    if not isinstance(d, dict):
        d = {}
    slots = [s for s in d.get("slots") or [] if isinstance(s, dict) and s.get("label") in SLOTS
             and isinstance(s.get("value"), str)]
    return {"intent": d.get("intent") if d.get("intent") in INTENTS else "out_of_scope",
            "department": d.get("department") if d.get("department") in DEPARTMENTS + [NO_DEPARTMENT]
            else NO_DEPARTMENT,
            "slots": slots, "valid_json": bool(d)}


def slot_sets(row, pred_slots):
    """Gold and predicted entities as (label, start, end) on gold tokens; unfound values → misses."""
    gold = entities(row["tags"])
    if "tags" in pred_slots:  # a tagger (baseline CRF, XLM-R) gives BIO tags directly
        return gold, entities(pred_slots["tags"]), 0
    pred, used, unfound = set(), set(), 0
    for s in pred_slots:
        span = locate(row["tokens"], s["value"], used)
        if span is None:
            unfound += 1
            continue
        used.add(span)
        pred.add((s["label"], *span))
    return gold, pred, unfound


def f1(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return 2 * p * r / (p + r) if p + r else 0.0


def macro_f1(golds, preds):
    labels = sorted(set(golds))
    out = []
    for lab in labels:
        tp = sum(g == lab and p == lab for g, p in zip(golds, preds))
        fp = sum(g != lab and p == lab for g, p in zip(golds, preds))
        fn = sum(g == lab and p != lab for g, p in zip(golds, preds))
        out.append(f1(tp, fp, fn))
    return sum(out) / len(out) if out else 0.0


def score(rows, preds):
    """Same metrics as baseline.py (sklearn macro-F1 when sklearn is installed)."""
    n = len(rows)
    golds = [r["intent"] for r in rows]
    ips = [p["intent"] for p in preds]
    routed = [i for i, r in enumerate(rows) if r["department"] != NO_DEPARTMENT]
    tp = fp = fn = 0
    rtp = rfp = rfn = 0
    for r, p in zip(rows, preds):
        gold, pred, unfound = slot_sets(r, p.get("tagged") or p["slots"])
        tp += len(gold & pred)
        fp += len(pred - gold) + unfound
        fn += len(gold - pred)
        # relaxed: same label and any token overlap, each gold matched at most once
        left = set(gold)
        for lab, s, e in pred:
            m = next((g for g in left if g[0] == lab and g[1] < e and s < g[2]), None)
            if m:
                left.discard(m)
                rtp += 1
            else:
                rfp += 1
        rfp += unfound
        rfn += len(left)
    try:
        from sklearn.metrics import f1_score
        mf1 = f1_score(golds, ips, average="macro")
    except ImportError:
        mf1 = macro_f1(golds, ips)
    return {
        "n": n,
        "intent_acc": round(sum(g == p for g, p in zip(golds, ips)) / n, 4),
        "intent_macro_f1": round(mf1, 4),
        "dept_top1_acc": round(sum(rows[i]["department"] == preds[i]["department"] for i in routed)
                               / len(routed), 4) if routed else None,
        "slot_entity_f1": round(f1(tp, fp, fn), 4),
        "slot_relaxed_f1": round(f1(rtp, rfp, rfn), 4),
    }


def score_by_script(rows, preds):
    out = {"overall": score(rows, preds)}
    by = defaultdict(list)
    for i, r in enumerate(rows):
        by[r["script"]].append(i)
    for s, idx in sorted(by.items()):
        out[s] = score([rows[i] for i in idx], [preds[i] for i in idx])
    return out


# ---------------------------------------------------------------- data

def load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8")]


def test_sample(rows, n, seed=13):
    """Stratified by script x intent so every slice keeps its share. n<=0 keeps all rows."""
    if n <= 0 or n >= len(rows):
        return rows
    rng = random.Random(seed)
    groups = defaultdict(list)
    for r in rows:
        groups[(r["script"], r["intent"])].append(r)
    picked, rest = [], []
    for key in sorted(groups):
        g = groups[key][:]
        rng.shuffle(g)
        k = max(1, round(len(g) * n / len(rows)))
        picked += g[:k]
        rest += g[k:]
    rng.shuffle(picked)
    rng.shuffle(rest)
    return sorted((picked + rest)[:n], key=lambda r: r["id"])


# ---------------------------------------------------------------- main

def run_set(name, rows, backend, out, cost_fn):
    pred_path = out / f"predictions_{name}.jsonl"
    done = {}
    if pred_path.exists():
        for line in open(pred_path, encoding="utf-8"):
            d = json.loads(line)
            done[d["id"]] = d
    with open(pred_path, "a", encoding="utf-8") as f:
        for k, r in enumerate(rows):
            if r["id"] in done:
                continue
            for attempt in range(5):
                try:
                    t0 = time.perf_counter()
                    reply, usage = backend(r["text"])
                    dt = time.perf_counter() - t0
                    break
                except Exception as e:  # rate limits, timeouts: back off and retry
                    if attempt == 4:
                        raise
                    wait = 2 ** attempt * 5
                    print(f"  error on {r['id']}: {e!r}; retrying in {wait}s", flush=True)
                    time.sleep(wait)
            d = {"id": r["id"], "reply": reply, "latency_s": round(dt, 3), **usage}
            done[r["id"]] = d
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
            f.flush()
            if (k + 1) % 20 == 0:
                print(f"  {name}: {k + 1}/{len(rows)}  last {dt:.2f}s", flush=True)
    recs = [done[r["id"]] for r in rows]
    preds = [parse_reply(d["reply"]) for d in recs]
    res = score_by_script(rows, preds)
    lat = [d["latency_s"] for d in recs]
    lat_sorted = sorted(lat)
    res["runtime"] = {
        "latency_mean_s": round(statistics.mean(lat), 3),
        "latency_median_s": round(statistics.median(lat), 3),
        "latency_p95_s": round(lat_sorted[int(0.95 * (len(lat) - 1))], 3),
        "tokens_in_mean": round(statistics.mean(d["in"] for d in recs), 1),
        "tokens_cached_in_mean": round(statistics.mean(d["cached_in"] for d in recs), 1),
        "tokens_out_mean": round(statistics.mean(d["out"] for d in recs), 1),
        "invalid_json": sum(not p["valid_json"] for p in preds),
        **cost_fn(recs),
    }
    errors = [{"id": r["id"], "script": r["script"], "text": r["text"],
               "gold": gold_json(r), "pred": {k: p[k] for k in ("intent", "department", "slots")}}
              for r, p in zip(rows, preds)
              if p["intent"] != r["intent"] or (r["department"] != NO_DEPARTMENT and p["department"] != r["department"])]
    with open(out / f"errors_{name}.jsonl", "w", encoding="utf-8") as f:
        for e in errors:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", choices=["anthropic", "openai", "llamacpp"], required=True)
    ap.add_argument("--model", required=True, help="model id, or path to a .gguf file for llamacpp")
    ap.add_argument("--shots", choices=["zero", "few"], default="few")
    ap.add_argument("--data", default=str(HERE.parent / "data" / "dataset_v1"))
    ap.add_argument("--sets", default="test,freeform", help="comma list of test and/or freeform")
    ap.add_argument("--test_n", type=int, default=300, help="stratified sample of test.jsonl; 0 = all 1,451")
    ap.add_argument("--out", required=True)
    ap.add_argument("--price_in", type=float, help="USD per 1M input tokens (default: known Claude prices)")
    ap.add_argument("--price_out", type=float, help="USD per 1M output tokens")
    ap.add_argument("--json_mode", choices=["schema", "object"], default="schema",
                    help="openai backend: use 'object' for servers without json_schema support")
    ap.add_argument("--threads", type=int, help="llamacpp CPU threads")
    a = ap.parse_args()

    data = Path(a.data)
    train = load(data / "train.jsonl")
    shots = pick_fewshot(train) if a.shots == "few" else []
    system = system_prompt(shots)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "config.json").write_text(json.dumps({**vars(a), "n_fewshot": len(shots),
                                                 "fewshot_ids": [r["id"] for r in shots]}, indent=2))
    (out / "system_prompt.txt").write_text(system, encoding="utf-8")

    if a.backend == "anthropic":
        backend = AnthropicBackend(a.model, system)
    elif a.backend == "openai":
        backend = OpenAIBackend(a.model, system, a.json_mode)
    else:
        backend = LlamaCppBackend(a.model, system, threads=a.threads)

    pin, pout = PRICES.get(a.model, (None, None))
    pin = a.price_in if a.price_in is not None else pin
    pout = a.price_out if a.price_out is not None else pout

    def cost_fn(recs):
        if pin is None or pout is None:
            return {"usd_per_message": 0.0 if a.backend == "llamacpp" else None,
                    "usd_per_1k_messages": 0.0 if a.backend == "llamacpp" else None}
        usd = [(d["in"] * pin + d["cached_in"] * pin * CACHE_READ_FACTOR + d["out"] * pout) / 1e6 for d in recs]
        m = statistics.mean(usd)
        return {"usd_per_message": round(m, 6), "usd_per_1k_messages": round(m * 1000, 3)}

    sets = {"test": test_sample(load(data / "test.jsonl"), a.test_n),
            "freeform": load(data / "test_freeform.jsonl")}
    results = {}
    for name in a.sets.split(","):
        print(f"== {name}: {len(sets[name])} messages, {a.shots}-shot, {a.model}", flush=True)
        results[name] = run_set(name, sets[name], backend, out, cost_fn)
        print(f"{'split':8} {'n':>4} {'int_acc':>8} {'int_F1':>7} {'dept':>6} {'slot_F1':>8} {'relaxed':>8}")
        for k, v in results[name].items():
            if k != "runtime":
                print(f"{k:8} {v['n']:>4} {v['intent_acc']:>8} {v['intent_macro_f1']:>7} "
                      f"{str(v['dept_top1_acc']):>6} {v['slot_entity_f1']:>8} {v['slot_relaxed_f1']:>8}")
        print("runtime", json.dumps(results[name]["runtime"]))
    (out / "scores.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
