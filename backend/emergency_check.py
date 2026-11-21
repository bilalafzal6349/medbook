"""Safety check: does the bot give the 1122 advice for every held-out emergency message, and how often
does it give it for messages that are not emergencies (false alarms)?

    python emergency_check.py        # uses whichever NLU engine the backend would load
"""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("MEDBOOK_NOW", "2026-11-23T09:00")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from clinic_db import Clinic  # noqa: E402
from dialogue import DialogueManager  # noqa: E402
from nlu import NLU  # noqa: E402

data = HERE.parent / "data" / "dataset_v2"
rows = [json.loads(l) for f in ("test.jsonl", "test_freeform.jsonl") for l in open(data / f, encoding="utf-8")]
clinic = Clinic(Path(tempfile.mkdtemp()) / "e.db")
dm = DialogueManager(NLU(clinic.doctors()), clinic)
res = {}
for name, sel in (("test", "template"), ("freeform", "freeform")):
    sub = [r for r in rows if (r["source"] == "freeform") == (sel == "freeform")]
    emg = [r for r in sub if r["intent"] == "emergency"]
    other = [r for r in sub if r["intent"] != "emergency"]
    hit = sum("1122" in dm.handle(f"e{i}", r["text"])["reply"] for i, r in enumerate(emg))
    fa = sum("1122" in dm.handle(f"o{i}", r["text"])["reply"] for i, r in enumerate(other))
    res[name] = {"emergency_msgs": len(emg), "recall": round(hit / len(emg), 3),
                 "other_msgs": len(other), "false_alarm_rate": round(fa / len(other), 3)}
res["engine"] = dm.nlu.engine_name
print(json.dumps(res, indent=2))
out = HERE.parent / "results" / "dialogue_sim" / f"emergency_{dm.nlu.engine_name}.json"
out.write_text(json.dumps(res, indent=2))
