"""Department routing accuracy, the way the dialogue manager routes (doctor name > department name > symptom).

    python route_eval.py      # model only vs model + keyword backstop, by split and script

Writes ../results/dialogue_sim/routing_<engine>.json
"""
import json
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from clinic_db import Clinic  # noqa: E402
from dialogue import department_from_name  # noqa: E402
from nlu import NLU  # noqa: E402
from routing import CHILD_MAX_AGE, age_years, route  # noqa: E402

data = HERE.parent / "data" / "dataset_v2"
clinic = Clinic(Path(tempfile.mkdtemp()) / "r.db")
nlu = NLU(clinic.doctors())
out = {"engine": nlu.engine_name}
for split in ("val", "test", "test_freeform"):
    rows = [json.loads(l) for l in open(data / f"{split}.jsonl", encoding="utf-8")]
    rows = [r for r in rows if r["department"] != "none"]
    acc = defaultdict(lambda: [0, 0, 0])     # script -> [n, model_ok, combined_ok]
    changed = []
    # Label noise found while building the keyword rules: some generated rows say "my younger brother, age 45"
    # and are labelled pediatrics. Count them separately; the "clean" scores leave them out.
    noisy = 0
    for r in rows:
        age = age_years(r["text"])
        bad_label = r["department"] == "pediatrics" and age is not None and age > CHILD_MAX_AGE
        noisy += bad_label
        p = nlu.parse(r["text"])
        slots = {s["label"]: s["value"] for s in p["slots"]}
        fixed = None
        if p["rules"].get("doctor_id"):
            fixed = clinic.doctor(p["rules"]["doctor_id"])["department"]
        elif "DEPARTMENT" in slots:
            fixed = department_from_name(slots["DEPARTMENT"])
        md, mc = (p["department"], p["department_conf"]) if p.get("department") else nlu.department_of(r["text"])
        model = fixed or md
        comb = fixed or route(r["text"], md, mc)[0]
        for k in (r["script"], "all") + (() if bad_label else ("all_clean",)):
            a = acc[k]
            a[0] += 1
            a[1] += model == r["department"]
            a[2] += comb == r["department"]
        if model != comb:
            changed.append({"text": r["text"], "gold": r["department"], "model": model, "combined": comb})
    out[split] = {k: {"n": n, "model_only": round(m / n, 3), "with_keywords": round(c / n, 3)}
                  for k, (n, m, c) in sorted(acc.items())}
    out[split]["adult_rows_labelled_pediatrics"] = noisy
    out[split]["changed_by_keywords"] = {"total": len(changed),
                                         "fixed": sum(c["combined"] == c["gold"] for c in changed),
                                         "broken": sum(c["model"] == c["gold"] for c in changed)}
    out[split + "_changes"] = changed
print(json.dumps({k: v for k, v in out.items() if not k.endswith("_changes")}, indent=2))
(HERE.parent / "results" / "dialogue_sim" / f"routing_{nlu.engine_name}.json").write_text(
    json.dumps(out, indent=2, ensure_ascii=False))
