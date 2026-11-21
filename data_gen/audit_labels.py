"""Rule-based label audit for a MedBook dataset folder.

Usage:
    python audit_labels.py ../data/dataset_v2            # prints counts, exits 1 if any hard slip
    python audit_labels.py ../data/dataset_v2 --show 5   # also prints examples of each check

Hard checks (must be zero):
    child_adult_age      child word + stated age over 12, but labelled pediatrics
    child_young_not_ped  child word + age 12 or under (or no age), routed, not pediatrics
    two_ages             a child phrase that carries its own age plus a second AGE slot
    male_gynecology      a male patient (abbu, a male name) or male speaker routed to gynecology
    adult_pediatrics     ammi / abbu routed to pediatrics
Soft check (printed for reading, not an error):
    keyword_disagrees    backend keyword router gives a different department than the label
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from routing import CHILD_MAX_AGE, _CHILD, age_years, keyword_department  # noqa: E402
import lexicons as L  # noqa: E402

MALE_NAMES = {n for st in ("roman", "urdu") for n in L.PATIENT_NAME[st]} - L.FEMALE_NAMES

ROUTED = {"book_appointment", "describe_symptom", "doctor_availability"}
MALE = re.compile(r"\babbu\b|\bابو\b|\bchahta\b|\bsakta\b|\bچاہتا\b|\bسکتا\b|سکوں گا|\bdada\b|\bnana\b", re.I)
ADULT_REL = re.compile(r"\bammi\b|\babbu\b|\bامی\b|\bابو\b", re.I)
AGE_IN_CHILD = re.compile(r"\d+\s*saal ke bet", re.I)


def checks(r):
    t, d = r["text"], r["department"]
    if r["intent"] not in ROUTED or d == "none":
        return []
    out = []
    child = _CHILD.search(t)
    age_spans = [s for s in r["spans"] if s["label"] == "AGE"]
    age = age_years(age_spans[0]["value"]) if age_spans else age_years(t)
    if child and age is not None and age > CHILD_MAX_AGE and d == "pediatrics":
        out.append("child_adult_age")
    if child and (age is None or age <= CHILD_MAX_AGE) and d != "pediatrics" and not MALE.search(t) \
            and d != "gynecology":
        out.append("child_young_not_ped")
    if AGE_IN_CHILD.search(t) and age_spans:
        out.append("two_ages")
    male_name = any(sp["label"] == "PATIENT_NAME" and sp["value"].lower() in {m.lower() for m in MALE_NAMES}
                    for sp in r["spans"])
    if (MALE.search(t) or male_name) and d == "gynecology":
        out.append("male_gynecology")
    if ADULT_REL.search(t) and d == "pediatrics":
        out.append("adult_pediatrics")
    kd, _ = keyword_department(t)
    if kd and kd != d:
        out.append("keyword_disagrees")
    return out


HARD = ["child_adult_age", "child_young_not_ped", "two_ages", "male_gynecology", "adult_pediatrics"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("--show", type=int, default=0)
    a = ap.parse_args()
    bad = 0
    for split in ("train", "val", "test", "test_freeform"):
        p = Path(a.data) / f"{split}.jsonl"
        rows = [json.loads(x) for x in open(p, encoding="utf-8")]
        found = defaultdict(list)
        for r in rows:
            for c in checks(r):
                found[c].append(r)
        print(f"{split:14s} rows={len(rows):5d} " + " ".join(f"{c}={len(found[c])}" for c in HARD + ["keyword_disagrees"]))
        bad += sum(len(found[c]) for c in HARD)
        if a.show:
            for c, rs in found.items():
                for r in rs[:a.show]:
                    print(f"   [{c}] {r['department']:18s} {r['text']}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
