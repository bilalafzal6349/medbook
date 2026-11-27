"""Rule-based vs LLM dialogue manager, side by side, from simulate.py results.

    python simulate.py --n 300                       # rules, template openers
    python simulate.py --n 300 --freeform            # rules, free-form openers
    python simulate.py --n 300 --dm llm              # LLM (needs ANTHROPIC_API_KEY), about $1 on Haiku 5.5
    python simulate.py --n 300 --dm llm --freeform
    python dm_compare.py                             # writes ../results/dialogue_sim/llm_vs_rules.md

Both managers get the same simulated users (same seed, same openers and answers) and the same NLU (XLM-R if
its weights are present, else the baseline), and success is checked in the database.
"""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def pct(x):
    return "-" if x is None else f"{100 * x:.1f}%"


def row(label, dm, r):
    t = r["by_task"]
    cost = f"${r['cost_usd_per_1000_dialogues']:.2f}" if "cost_usd_per_1000_dialogues" in r else "$0"
    return (f"| {label} | {dm} | {pct(r['overall']['success'])} | {pct(t['book']['success'])} | "
            f"{pct(t['cancel']['success'])} | {pct(t['reschedule']['success'])} | {pct(r['by_script']['urdu']['success'])} | "
            f"{r['overall']['avg_turns']} | {r.get('turn_ms_median', '-')} ms | {r['invented_booking_numbers']} | {cost} |")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(HERE.parent / "results" / "dialogue_sim"))
    ap.add_argument("--engine", default="xlmr")
    a = ap.parse_args()
    d = Path(a.dir)
    lines = ["| Openers | Dialogue manager | Task success | Book | Cancel | Reschedule | Urdu-script | Avg turns | "
             "Median turn time | Invented booking numbers | Cost per 1000 dialogues |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for openers, suf in (("Test templates", ""), ("Free-form", "_freeform")):
        for dm, name in (("Rules", f"{a.engine}{suf}"), ("LLM", f"{a.engine}_llm{suf}")):
            f = d / f"{name}.json"
            if f.exists():
                r = json.loads(f.read_text())
                lines.append(row(openers, dm + (f" ({r['llm_model']})" if r.get("llm_model") else ""), r))
            else:
                lines.append(f"| {openers} | {dm} | not run yet (`{f.name}` missing) |||||||||")
    out = d / "llm_vs_rules.md"
    out.write_text("# Rule-based vs LLM dialogue manager (simulate.py, 300 dialogues, seed 7)\n\n" + "\n".join(lines) + "\n")
    print("\n".join(lines))
    print("\nwritten to", out)


if __name__ == "__main__":
    main()
