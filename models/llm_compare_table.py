"""Collect every results/llm_compare/*/scores.json into Markdown tables.

    python llm_compare_table.py > ../results/llm_compare/tables.md
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "results" / "llm_compare"
ORDER = ["baseline", "xlmr"]  # then the LLM runs, alphabetically
NAMES = {"baseline": "Baseline (TF-IDF + LR, CRF)", "xlmr": "XLM-R fine-tuned (final model)"}


def name_of(run):
    if run in NAMES:
        return NAMES[run]
    model, _, shots = run.rpartition("_")
    return f"{model} {shots}-shot"


def fmt(x):
    return "n/a" if x is None else f"{x:.2f}"


def main():
    runs = sorted((p.parent for p in ROOT.glob("*/scores.json")),
                  key=lambda p: (ORDER.index(p.name) if p.name in ORDER else 9, p.name))
    if not runs:
        sys.exit(f"no scores.json under {ROOT}")
    res = {p.name: json.loads((p / "scores.json").read_text()) for p in runs}
    for tset, title in [("freeform", "Free-form set (145 hand-written messages)"),
                        ("test", "Unseen-template test, stratified sample (300 messages)")]:
        rows = [r for r in res if tset in res[r]]
        if not rows:
            continue
        print(f"### {title}\n")
        print("| Model | Intent acc | Intent macro-F1 | Department acc | Slot F1 (exact) | Slot F1 (relaxed) |")
        print("| --- | --- | --- | --- | --- | --- |")
        for r in rows:
            o = res[r][tset]["overall"]
            print(f"| {name_of(r)} | {fmt(o['intent_acc'])} | {fmt(o['intent_macro_f1'])} | "
                  f"{fmt(o['dept_top1_acc'])} | {fmt(o['slot_entity_f1'])} | {fmt(o.get('slot_relaxed_f1'))} |")
        print(f"\n**By writing style ({tset}): intent accuracy / department accuracy / exact slot F1**\n")
        print("| Model | Roman Urdu | Urdu script | Urdu + English (mixed) |")
        print("| --- | --- | --- | --- |")
        for r in rows:
            cells = []
            for s in ("roman", "urdu", "mixed"):
                v = res[r][tset].get(s)
                cells.append(f"{fmt(v['intent_acc'])} / {fmt(v['dept_top1_acc'])} / {fmt(v['slot_entity_f1'])}"
                             if v else "n/a")
            print(f"| {name_of(r)} | " + " | ".join(cells) + " |")
        print()
    print("### Latency and cost per message\n")
    print("| Model | Hardware | Median latency | p95 latency | Tokens in / out | Cost per 1,000 messages |")
    print("| --- | --- | --- | --- | --- | --- |")
    for r in res:
        rt = next((res[r][t]["runtime"] for t in ("freeform", "test") if t in res[r]), None)
        if not rt:
            continue
        hw = "CPU, 4 cores" if r in ORDER or "qwen" in r else "API"
        tok = (f"{rt['tokens_in_mean']:.0f} / {rt['tokens_out_mean']:.0f}" if "tokens_in_mean" in rt else "n/a")
        usd = rt.get("usd_per_1k_messages")
        cost = "n/a" if usd is None else ("$0 (local)" if usd == 0 else f"${usd:.2f}")
        med, p95 = rt["latency_median_s"], rt["latency_p95_s"]
        lat = (lambda s: f"{s * 1000:.0f} ms" if s < 1 else f"{s:.1f} s")
        print(f"| {name_of(r)} | {hw} | {lat(med)} | {lat(p95)} | {tok} | {cost} |")


if __name__ == "__main__":
    main()
