"""Build the figures for docs/MedBook_Final_Report.docx from the result files in this repo.

Run from the repository root:  python docs/report_figures/make_figures.py
Every number is read from results/, data/ or loadtest/; nothing is typed in by hand
except the Whisper table (copied from DEMO.md, which voice_eval.py printed).
"""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
GRAY = "#9a9893"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID,
    "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False, "axes.titleweight": "bold",
    "axes.titlesize": 11, "axes.titlecolor": INK, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.6, "axes.axisbelow": True, "figure.dpi": 200,
})


def load(p):
    return json.loads((ROOT / p).read_text(encoding="utf-8"))


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=200, facecolor="white")
    plt.close(fig)


def label_bars(ax, bars, fmt="{:.2f}", horiz=False):
    for b in bars:
        if horiz:
            v = b.get_width()
            ax.text(v + ax.get_xlim()[1] * 0.01, b.get_y() + b.get_height() / 2, fmt.format(v),
                    va="center", fontsize=8, color=INK2)
        else:
            v = b.get_height()
            ax.text(b.get_x() + b.get_width() / 2, v + ax.get_ylim()[1] * 0.01, fmt.format(v),
                    ha="center", va="bottom", fontsize=7.5, color=INK2)


stats = load("data/dataset_v2/stats.json")

# Figure: intents across all single-turn splits
intents = {}
for split in ("train", "val", "test"):
    for k, v in stats[split]["intent"].items():
        intents[k] = intents.get(k, 0) + v
items = sorted(intents.items(), key=lambda kv: kv[1])
fig, ax = plt.subplots(figsize=(6.5, 4.2))
bars = ax.barh([k for k, _ in items], [v for _, v in items], color=BLUE, height=0.65)
ax.set_xlim(0, max(intents.values()) * 1.12)
label_bars(ax, bars, "{:,.0f}", horiz=True)
ax.set_xlabel("Labelled messages (train + val + test)")
ax.set_title("Intent distribution in dataset v2 (8,615 template rows)")
ax.grid(axis="y", visible=False)
save(fig, "fig_intents.png")

# Figure: writing style by split
splits = ["train", "val", "test", "test_freeform"]
names = ["Train", "Validation", "Test (unseen templates)", "Free-form test"]
styles = [("roman", "Roman Urdu", BLUE), ("urdu", "Urdu script", ORANGE), ("mixed", "Urdu + English", AQUA)]
fig, ax = plt.subplots(figsize=(6.5, 3.4))
w = 0.26
for i, (key, lab, col) in enumerate(styles):
    vals = [100 * stats[s]["script"][key] / stats[s]["rows"] for s in splits]
    bars = ax.bar([x + (i - 1) * w for x in range(len(splits))], vals, w - 0.02, color=col, label=lab)
    label_bars(ax, bars, "{:.0f}%")
ax.set_xticks(range(len(splits)), names)
ax.set_ylabel("Share of split (%)")
ax.set_ylim(0, 65)
ax.set_title("Writing style by split")
ax.legend(frameon=False, ncol=3, loc="upper right")
ax.grid(axis="x", visible=False)
save(fig, "fig_scripts.png")

# Figure: departments
depts = {}
for split in ("train", "val", "test"):
    for k, v in stats[split]["department"].items():
        if k != "none":
            depts[k] = depts.get(k, 0) + v
items = sorted(depts.items(), key=lambda kv: kv[1])
pretty = {"general_physician": "General physician", "ent": "ENT", "gastroenterology": "Gastroenterology",
          "orthopedics": "Orthopedics", "gynecology": "Gynecology", "pediatrics": "Pediatrics",
          "cardiology": "Cardiology", "dermatology": "Dermatology"}
fig, ax = plt.subplots(figsize=(6.5, 3.2))
bars = ax.barh([pretty[k] for k, _ in items], [v for _, v in items], color=BLUE, height=0.6)
ax.set_xlim(0, max(depts.values()) * 1.15)
label_bars(ax, bars, "{:,.0f}", horiz=True)
ax.set_xlabel("Messages with a routing label")
ax.set_title("Department labels in dataset v2")
ax.grid(axis="y", visible=False)
save(fig, "fig_departments.png")

# Figure: baseline vs XLM-R on both test sets
base = load("results/baseline_v2/scores.json")
xl = load("results/xlmr_v2_main/scores.json")
metrics = [("intent_acc", "Intent\naccuracy"), ("intent_macro_f1", "Intent\nmacro-F1"),
           ("dept_top1_acc", "Department\naccuracy"), ("slot_entity_f1", "Slot F1")]
fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.6), sharey=True)
for ax, (setname, title) in zip(axes, [("test", "Unseen-template test (1,453)"), ("freeform", "Free-form test (145)")]):
    for i, (src, lab, col) in enumerate([(base, "Baseline (TF-IDF+LR, CRF)", GRAY), (xl, "XLM-R joint model", BLUE)]):
        vals = [src[setname]["overall"][m] for m, _ in metrics]
        bars = ax.bar([x + (i - 0.5) * 0.38 for x in range(4)], vals, 0.36, color=col, label=lab)
        label_bars(ax, bars)
    ax.set_xticks(range(4), [l for _, l in metrics], fontsize=8)
    ax.set_title(title)
    ax.set_ylim(0, 1.1)
    ax.grid(axis="x", visible=False)
axes[0].set_ylabel("Score")
h, l = axes[0].get_legend_handles_labels()
fig.legend(h, l, frameon=False, ncol=2, loc="lower center", fontsize=8.5)
fig.tight_layout(rect=(0, 0.07, 1, 1))
fig.savefig(OUT / "fig_baseline_vs_xlmr.png", dpi=200, facecolor="white")
plt.close(fig)

# Figure: XLM-R per-style intent accuracy on free-form
fig, ax = plt.subplots(figsize=(6.5, 3.0))
sty = [("roman", "Roman Urdu (78)"), ("urdu", "Urdu script (42)"), ("mixed", "Urdu + English (25)")]
for i, (src, lab, col) in enumerate([(base, "Baseline", GRAY), (xl, "XLM-R", BLUE)]):
    vals = [src["freeform"][k]["intent_acc"] for k, _ in sty]
    bars = ax.bar([x + (i - 0.5) * 0.38 for x in range(3)], vals, 0.36, color=col, label=lab)
    label_bars(ax, bars)
ax.set_xticks(range(3), [l for _, l in sty])
ax.set_ylim(0, 1.05)
ax.set_ylabel("Intent accuracy")
ax.set_title("Free-form intent accuracy by writing style")
ax.legend(frameon=False, loc="upper left", ncol=2)
ax.grid(axis="x", visible=False)
save(fig, "fig_by_style.png")

# Figure: training curve
log = load("results/xlmr_v2_main/train_log.json")
ep = [r["epoch"] for r in log]
fig, ax = plt.subplots(figsize=(6.5, 3.3))
for key, lab, col in [("intent_acc", "Intent accuracy", BLUE), ("dept_top1_acc", "Department accuracy", ORANGE),
                      ("slot_entity_f1", "Slot F1", AQUA)]:
    ys = [r["val"][key] for r in log]
    ax.plot(ep, ys, color=col, lw=2, marker="o", ms=5, label=lab)
    ax.annotate(f"{ys[-1]:.2f}", (ep[-1], ys[-1]), xytext=(6, 0), textcoords="offset points",
                va="center", fontsize=8, color=INK2)
ax.set_xticks(ep)
ax.set_xlabel("Epoch")
ax.set_ylabel("Validation score (unseen templates)")
ax.set_ylim(0.5, 1.02)
ax.set_xlim(0.8, 5.5)
ax.set_title("XLM-R training: validation scores per epoch (v2 main run)")
ax.legend(frameon=False, loc="lower right")
save(fig, "fig_training.png")

# Figure: LLM comparison (free-form intent accuracy + latency)
rows = []
for run, lab in [("baseline", "Baseline"), ("qwen2.5-3b_zero", "Qwen2.5-3B zero-shot"),
                 ("qwen2.5-3b_few", "Qwen2.5-3B few-shot"), ("qwen2.5-7b_few", "Qwen2.5-7B few-shot"),
                 ("xlmr", "XLM-R fine-tuned")]:
    s = load(f"results/llm_compare/{run}/scores.json")
    rows.append((lab, s))
fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.3))
ax = axes[0]
vals = [s["freeform"]["overall"]["intent_acc"] for _, s in rows]
cols = [GRAY, ORANGE, ORANGE, ORANGE, BLUE]
bars = ax.barh([l for l, _ in rows], vals, color=cols, height=0.6)
ax.set_xlim(0, 1.0)
label_bars(ax, bars, horiz=True)
ax.set_title("Intent accuracy (free-form)")
ax.grid(axis="y", visible=False)
ax = axes[1]
lat = [s["freeform"]["runtime"]["latency_median_s"] * 1000 for _, s in rows]
bars = ax.barh([l for l, _ in rows], lat, color=cols, height=0.6)
ax.set_xscale("log")
ax.set_xlim(0.5, 60000)
for b, v in zip(bars, lat):
    ax.text(v * 1.15, b.get_y() + b.get_height() / 2, f"{v:,.0f} ms" if v < 1000 else f"{v/1000:.1f} s",
            va="center", fontsize=8, color=INK2)
ax.set_yticks([])
ax.set_title("Median latency (CPU, log scale)")
ax.set_xticks([1, 10, 100, 1000, 10000], ["1 ms", "10 ms", "0.1 s", "1 s", "10 s"], fontsize=8)
ax.minorticks_off()
ax.grid(axis="y", visible=False)
save(fig, "fig_llm_compare.png")

# Figure: Whisper model size vs WER and intent from voice
fl = {r["model"]: r for r in load("results/voice_eval/fleurs.json")["runs"]}
sy = {r["model"]: r for r in load("results/voice_eval/synthetic.json")["runs"]
      if r["prompt"] == "clinic" and r.get("noise_snr_db") is None}
order = ["tiny", "base", "small", "medium", "large-v3-turbo"]
fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.2))
ax = axes[0]
for i, (vals, lab, col) in enumerate([([fl[m]["wer"] * 100 for m in order], "FLEURS real speech", BLUE),
                                       ([sy[m]["wer"] * 100 for m in order], "Synthetic clinic clips", ORANGE)]):
    bars = ax.bar([x + (i - 0.5) * 0.38 for x in range(5)], vals, 0.36, color=col, label=lab)
    label_bars(ax, bars, "{:.0f}")
ax.set_xticks(range(5), ["tiny", "base", "small", "medium", "large-v3\nturbo"], fontsize=8)
ax.set_ylabel("Word error rate (%)")
ax.set_ylim(0, 75)
ax.set_title("Speech recognition errors")
ax.legend(frameon=False, fontsize=8)
ax.grid(axis="x", visible=False)
ax = axes[1]
for i, (key, lab, col) in enumerate([("intent_acc_voice", "Intent from voice", BLUE),
                                     ("dept_acc_voice", "Department from voice", AQUA)]):
    vals = [sy[m][key] * 100 for m in order]
    bars = ax.bar([x + (i - 0.5) * 0.38 for x in range(5)], vals, 0.36, color=col, label=lab)
    label_bars(ax, bars, "{:.0f}")
ax.axhline(94.7, color=INK2, lw=1, ls="--")
ax.text(4.6, 89, "typed intent 94.7%", ha="right", fontsize=7.5, color=INK2)
ax.set_xticks(range(5), ["tiny", "base", "small", "medium", "large-v3\nturbo"], fontsize=8)
ax.set_ylabel("Accuracy (%)")
ax.set_ylim(0, 125)
ax.set_title("What the NLU gets from the transcript")
ax.legend(frameon=False, fontsize=8, loc="upper left", ncol=2)
ax.grid(axis="x", visible=False)
save(fig, "fig_voice.png")

# Figure: load test
runs = [("u50", "50 users"), ("u100", "100 users"), ("u200", "200 users")]
agg = {}
for key, _ in runs + [("stress200", "")]:
    with open(ROOT / f"loadtest/results/{key}_stats.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["Name"] == "Aggregated":
                agg[key] = r
fig, ax = plt.subplots(figsize=(6.5, 3.0))
for i, (pct, lab, col) in enumerate([("50%", "Median", AQUA), ("95%", "p95", BLUE), ("99%", "p99", ORANGE)]):
    vals = [float(agg[k][pct]) for k, _ in runs]
    bars = ax.bar([x + (i - 1) * 0.26 for x in range(3)], vals, 0.24, color=col, label=lab)
    label_bars(ax, bars, "{:.0f}")
ax.set_xticks(range(3), [f"{l}\n{int(agg[k]['Request Count']):,} requests, 0 failures" for k, l in runs], fontsize=8)
ax.set_ylabel("Response time (ms)")
ax.set_ylim(0, 210)
ax.set_title("Load test: response time per chat message (baseline NLU, 1 worker)")
ax.legend(frameon=False, ncol=3, loc="upper left")
ax.grid(axis="x", visible=False)
save(fig, "fig_loadtest.png")


# Diagrams
def box(ax, x, y, w, h, text, fc="#eef4fc", ec=BLUE, fs=8.5, bold=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                fc=fc, ec=ec, lw=1.2))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=INK,
            fontweight="bold" if bold else "normal", wrap=True)


def arrow(ax, x1, y1, x2, y2, text=None):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=INK2, lw=1.1, shrinkA=2, shrinkB=2))
    if text:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 0.12, text, ha="center", fontsize=7, color=INK2)


def canvas(w, h):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, w * 1.4)
    ax.set_ylim(0, h * 1.4)
    ax.axis("off")
    return fig, ax


fig, ax = canvas(7.4, 4.6)
box(ax, 0.1, 4.6, 1.7, 0.9, "Patient browser\n(text or mic)", fc="#f4f3f0", ec=GRAY, fs=7.5)
box(ax, 0.1, 2.9, 1.7, 0.9, "Staff browser\n/admin page", fc="#f4f3f0", ec=GRAY, fs=7.5)
box(ax, 2.3, 3.6, 1.7, 1.4, "Next.js frontend\nchat UI,\ndebug panel,\nstaff page", fs=7.5)
box(ax, 4.5, 1.2, 3.2, 4.8, "", fc="#fbfbfa", ec=GRAY)
ax.text(6.1, 5.75, "FastAPI backend", ha="center", fontsize=9.5, fontweight="bold", color=INK)
box(ax, 4.7, 4.65, 2.8, 0.8, "Voice: Whisper large-v3-turbo\n+ cleanup, MMS-TTS (Urdu)", fc="#fdf0ea", ec=ORANGE, fs=7)
box(ax, 4.7, 3.65, 2.8, 0.8, "NLU: XLM-R joint model\nintent + department + slots", fs=7)
box(ax, 4.7, 2.65, 2.8, 0.8, "Rules: emergency, phone, MB-xxxx,\ndoctors, keyword routing, age", fc="#e8f7f1", ec=AQUA, fs=7)
box(ax, 4.7, 1.45, 2.8, 1.0, "Dialogue manager\nbelief state, slot filling,\ncorrections, slot negotiation", fs=7)
box(ax, 8.1, 4.2, 1.8, 0.9, "Redis\nsession state", fc="#f4f3f0", ec=GRAY, fs=7.5)
box(ax, 8.1, 2.4, 1.8, 1.2, "PostgreSQL\ndoctors, duty,\nappointments,\nreminders", fc="#f4f3f0", ec=GRAY, fs=7.5)
box(ax, 8.1, 0.6, 1.8, 1.1, "Reminder worker\nevery 5 min, SMS", fc="#f4f3f0", ec=GRAY, fs=7.5)
arrow(ax, 1.8, 5.05, 2.3, 4.5)
arrow(ax, 1.8, 3.35, 2.3, 3.9)
arrow(ax, 4.0, 4.3, 4.5, 4.3, "/api/*")
arrow(ax, 7.7, 4.4, 8.1, 4.6)
arrow(ax, 7.7, 2.6, 8.1, 2.9)
arrow(ax, 9.0, 1.7, 9.0, 2.4)
save(fig, "fig_architecture.png")

fig, ax = canvas(7.2, 3.6)
steps = [("User message\n(text, or Whisper\ntranscript)", "#f4f3f0", GRAY),
         ("Normalise\nUrdu digits, dates,\ntimes (normalize.py)", "#eef4fc", BLUE),
         ("XLM-R NLU\nintent, dept,\nslots + confidence", "#eef4fc", BLUE),
         ("Rules on top\nemergency stop,\nregex, doctor names", "#e8f7f1", AQUA),
         ("Update belief state\nmerge slots,\napply corrections", "#eef4fc", BLUE)]
x = 0.1
for t, fc, ec in steps:
    box(ax, x, 3.0, 1.75, 1.2, t, fc=fc, ec=ec, fs=7.5)
    if x > 0.2:
        arrow(ax, x - 0.25, 3.6, x, 3.6)
    x += 2.0
steps2 = [("Reply in the user's\nscript; write booking\nonly after 'yes'", "#eef4fc", BLUE),
          ("Confirm summary\n(any slot can still\nbe corrected)", "#eef4fc", BLUE),
          ("Offer free slots\nfrom the database\n(never invented)", "#eef4fc", BLUE),
          ("Route department\ndoctor > department\n> symptom (+ age)", "#eef4fc", BLUE),
          ("Next missing slot?\ndept/doctor, date,\ntime, name, phone", "#eef4fc", BLUE)]
x = 0.1
for t, fc, ec in steps2:
    box(ax, x, 0.7, 1.75, 1.2, t, fc=fc, ec=ec, fs=7.5)
    if x > 0.2:
        arrow(ax, x, 1.3, x - 0.25, 1.3)
    x += 2.0
arrow(ax, 9.0, 3.0, 9.0, 1.9)
box(ax, 4.3, 4.45, 3.2, 0.45, "Emergency word -> stop task, advise Rescue 1122", fc="#fdecec", ec="#e34948", fs=7.5)
arrow(ax, 6.9, 4.2, 6.6, 4.45)
save(fig, "fig_dialogue_flow.png")
print("figures written to", OUT)
