"""Simulated-user evaluation of the whole system (NLU + dialogue manager + database).

A scripted user with a goal (book / cancel / reschedule) talks to the bot. The opening message is a
real row from the held-out test split (templates never seen in training), or from the free-form set
with --freeform. Short answers come from test rows too, falling back to val/train rows only when the
test split has no template for that slot in that script. The user answers whatever the bot waits for:

    bot waits for DEPARTMENT -> a describe_symptom row whose gold department is the goal department
    bot waits for DATE/TIME/PATIENT_NAME/PHONE/APPOINTMENT_ID -> an inform row carrying only that slot
    bot offers slots -> "1" / "pehla wala" / "دوسرا";  bot asks to confirm -> a confirm row

Success is checked in the database, not in the bot's words:
    book        a new booking exists, in the goal department
    cancel      the goal booking is cancelled
    reschedule  the goal booking moved to another day/time

    python simulate.py --n 300                 # writes ../results/dialogue_sim/<engine>.json
    python simulate.py --n 300 --dm llm        # same users, LLM dialogue manager (llm_agent.py), needs an API key
                                               # writes <engine>_llm.json with token counts and cost
"""
import argparse
import json
import os
import random
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

os.environ.setdefault("MEDBOOK_NOW", "2026-11-23T09:00")
os.environ["MEDBOOK_DB"] = str(Path(tempfile.mkdtemp()) / "sim.db")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from clinic_db import SEED_BOOKINGS, Clinic  # noqa: E402
from dialogue import DialogueManager  # noqa: E402
from nlu import NLU  # noqa: E402

MAX_TURNS = 14
PICKS = {"roman": ["1", "pehla wala", "2", "doosra wala theek hai"], "urdu": ["1", "پہلا والا", "دوسرا"],
         "mixed": ["1", "پہلا والا", "2"]}


def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8")]


class Pool:
    """Rows indexed by intent/script/slot set. `backup` pools are tried in order when this one has no match."""

    def __init__(self, rows, backup=()):
        self.backup = list(backup)
        self.rows = rows
        self.by = defaultdict(list)
        for r in rows:
            labels = frozenset(s["label"] for s in r["spans"])
            self.by[(r["intent"], r["script"])].append(r)
            self.by[(r["intent"], r["script"], labels)].append(r)

    def get(self, rng, intent, script, only=None, where=None):
        key = (intent, script, frozenset(only)) if only is not None else (intent, script)
        cands = [r for r in self.by.get(key, []) if not where or where(r)]
        if cands:
            return rng.choice(cands)
        for b in self.backup:
            r = b.get(rng, intent, script, only, where)
            if r:
                return r
        nxt = {"mixed": "urdu", "urdu": "roman"}.get(script)   # last resort: another script
        return self.get(rng, intent, nxt, only, where) if nxt else None


def with_ref(row, ref):
    """Swap the booking number in a row for one that exists in the seeded database."""
    t = row["text"]
    for s in row["spans"]:
        if s["label"] == "APPOINTMENT_ID":
            t = t.replace(s["value"], ref)
    return t


def run_one(rng, nlu, pool, openers, task, script, make_dm=None):
    clinic = Clinic(Path(tempfile.mkdtemp()) / "c.db")
    dm = make_dm(nlu, clinic) if make_dm else DialogueManager(nlu, clinic)
    ref = rng.choice(SEED_BOOKINGS)[0]
    before = clinic.appointment(ref)
    sid = "sim"
    if task == "book":
        opener = openers.get(rng, rng.choice(["book_appointment", "describe_symptom"]), script,
                             where=lambda r: r["department"] != "none") \
            or pool.get(rng, "book_appointment", script, where=lambda r: r["department"] != "none")
        gold_dept = opener["department"]
        text = opener["text"]
    else:
        intent = "cancel_appointment" if task == "cancel" else "reschedule_appointment"
        opener = pool.get(rng, intent, script)
        gold_dept = None
        text = with_ref(opener, ref)
    log, r = [], None
    for _ in range(MAX_TURNS):
        t0 = time.time()
        r = dm.handle(sid, text)
        log.append({"user": text, "bot": r["reply"], "intent": r["nlu"]["intent"], "awaiting": r["state"]["awaiting"],
                    "ms": round((time.time() - t0) * 1000), "tools": [c["name"] for c in r.get("tool_calls", [])]})
        a, t = r["state"]["awaiting"], r["state"]["task"]
        if t is None and a is None:
            break
        if a == "DEPARTMENT":
            row = pool.get(rng, "describe_symptom", script, where=lambda x: x["department"] == gold_dept)
        elif a in ("DATE", "TIME", "PATIENT_NAME", "PHONE"):
            row = pool.get(rng, "inform", script, only={a})
        elif a == "APPOINTMENT_ID":
            row = pool.get(rng, "inform", script, only={"APPOINTMENT_ID"})
            row = dict(row, text=with_ref(row, ref)) if row else None
        elif a == "slot_choice":
            row = {"text": rng.choice(PICKS[script])}
        elif a in ("confirm", "offer_one"):
            row = pool.get(rng, "confirm", script, only=set())
        elif a == "task_for_ref":
            row = pool.get(rng, "cancel_appointment" if task == "cancel" else
                           "reschedule_appointment" if task == "reschedule" else "book_appointment", script, only=set())
        else:   # "change" or anything unexpected: the user gives up
            break
        if row is None:
            break
        text = row["text"]
    # ---- judge on the database
    new = [x for x in clinic.all_appointments() if x["session_id"] == sid and x["status"] == "booked"]
    after = clinic.appointment(ref)
    if task == "book":
        ok = len(new) == 1 and new[0]["department"] == gold_dept
        routed = bool(new) and new[0]["department"] == gold_dept
    elif task == "cancel":
        ok, routed = after["status"] == "cancelled" and not new, None
    else:
        ok = after["status"] == "booked" and (after["day"], after["start_min"]) != (before["day"], before["start_min"])
        routed = None
    invented = [w for e in log for w in e["bot"].split() if w.startswith("MB-")
                and not clinic.appointment(w.strip(".,!?۔"))]
    from routing import CHILD_MAX_AGE, age_years
    age = age_years(opener["text"])
    noisy = gold_dept == "pediatrics" and age is not None and age > CHILD_MAX_AGE   # adult labelled pediatrics
    usage = getattr(dm.sessions.get(sid), "usage", None)
    return {"task": task, "script": script, "ok": ok, "usage": usage, "noisy_label": noisy, "routed": routed, "turns": len(log),
            "invented_refs": invented, "gold_dept": gold_dept, "log": log}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--freeform", action="store_true", help="take booking openers from the free-form set")
    ap.add_argument("--out", default=str(HERE.parent / "results" / "dialogue_sim"))
    ap.add_argument("--dm", choices=["rules", "llm"], default="rules", help="dialogue manager to test")
    ap.add_argument("--price_in", type=float, default=0.10, help="USD per 1M input tokens (Haiku 5.5)")
    ap.add_argument("--price_out", type=float, default=0.50, help="USD per 1M output tokens (Haiku 5.5)")
    a = ap.parse_args()
    data = HERE.parent / "data" / "dataset_v2"
    # openers come only from the held-out test split; short answers ("kal", "Ali", "0300...") fall back
    # to val, then train, when the test split has no template for that slot in that script.
    pool = Pool(load(data / "test.jsonl"), backup=[Pool(load(data / "val.jsonl")), Pool(load(data / "train.jsonl"))])
    openers = Pool(load(data / "test_freeform.jsonl")) if a.freeform else Pool(load(data / "test.jsonl"))
    nlu = NLU(Clinic(Path(tempfile.mkdtemp()) / "x.db").doctors())
    make_dm = None
    if a.dm == "llm":
        from llm_agent import LLMDialogueManager, make_provider
        provider = make_provider()
        make_dm = lambda n, c: LLMDialogueManager(n, c, provider)   # noqa: E731
    rng = random.Random(a.seed)
    res = []
    for i in range(a.n):
        task = rng.choices(["book", "cancel", "reschedule"], weights=[70, 15, 15])[0]
        script = rng.choice(["roman", "roman", "urdu", "mixed"])
        res.append(run_one(rng, nlu, pool, openers, task, script, make_dm))
        if a.dm == "llm":
            print(f"[{i + 1}/{a.n}] {task} {script}: {'ok' if res[-1]['ok'] else 'FAIL'} in {res[-1]['turns']} turns",
                  flush=True)

    def summ(rows):
        return {"n": len(rows), "success": round(sum(r["ok"] for r in rows) / len(rows), 3) if rows else None,
                "avg_turns": round(sum(r["turns"] for r in rows) / len(rows), 1) if rows else None}
    clean = [r for r in res if not r["noisy_label"]]
    report = {"engine": nlu.engine_name, "n": a.n, "openers": "freeform" if a.freeform else "test templates",
              "overall": summ(res),
              # dataset label noise: openers like "my younger brother, age 45, has fever" are labelled pediatrics
              "overall_without_adult_pediatrics_labels": summ(clean),
              "book_without_adult_pediatrics_labels": summ([r for r in clean if r["task"] == "book"]),
              "by_task": {t: summ([r for r in res if r["task"] == t]) for t in ("book", "cancel", "reschedule")},
              "by_script": {s: summ([r for r in res if r["script"] == s]) for s in ("roman", "urdu", "mixed")},
              "invented_booking_numbers": sum(len(r["invented_refs"]) for r in res),
              "turn_ms_median": sorted(e["ms"] for r in res for e in r["log"])[sum(len(r["log"]) for r in res) // 2],
              "failure_last_awaiting": Counter(r["log"][-1]["awaiting"] or "none" for r in res if not r["ok"]).most_common()}
    if a.dm == "llm":
        u = Counter()
        for r in res:
            u.update(r["usage"] or {})
        tin = u["input"] + u["cache_read"] * 0.1 + u["cache_write"] * 1.25   # cache reads 10%, writes 125%
        report["dm"] = "llm"
        report["llm_model"] = provider.model
        report["llm_usage"] = dict(u)
        report["llm_calls_per_dialogue"] = round(u["llm_calls"] / a.n, 1)
        report["cost_usd"] = round((tin * a.price_in + u["output"] * a.price_out) / 1e6, 4)
        report["cost_usd_per_1000_dialogues"] = round(report["cost_usd"] * 1000 / a.n, 2)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    name = f"{nlu.engine_name}{'_llm' if a.dm == 'llm' else ''}{'_freeform' if a.freeform else ''}"
    (out / f"{name}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    with open(out / f"{name}_failures.jsonl", "w", encoding="utf-8") as f:
        for r in res:
            if not r["ok"]:
                f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
