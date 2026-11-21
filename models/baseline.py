"""Classical baselines: TF-IDF + logistic regression (intent, department) and CRF (slots).

Usage:
    pip install scikit-learn sklearn-crfsuite
    python baseline.py --data ../data/sample --out ../results/baseline

Reports overall and per-script (roman / urdu / mixed) scores on the test split.
These are the numbers the fine-tuned XLM-R model has to beat.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

import sklearn_crfsuite
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import make_pipeline


def load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8")]


def text_clf():
    # char n-grams handle Roman spelling variants (chahiye / chahye) and Urdu script alike
    return make_pipeline(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, min_df=1),
        LogisticRegression(max_iter=2000, C=5.0),
    )


def tok_features(tokens, i):
    w = tokens[i]
    f = {"w": w.lower(), "suf3": w[-3:], "pre3": w[:3], "digit": w.isdigit(),
         "title": w.istitle(), "latin": w.isascii(), "len": min(len(w), 8)}
    for d in (-2, -1, 1, 2):
        j = i + d
        f[f"w{d}"] = tokens[j].lower() if 0 <= j < len(tokens) else "<pad>"
    return f


def entities(tags):
    ents, cur = set(), None
    for i, t in enumerate(tags + ["O"]):
        if t.startswith("B-") or t == "O" or (t.startswith("I-") and (not cur or cur[0] != t[2:])):
            if cur:
                ents.add((cur[0], cur[1], i))
            cur = (t[2:], i) if t != "O" else None
    return ents


def entity_f1(gold_seqs, pred_seqs):
    tp = fp = fn = 0
    for g, p in zip(gold_seqs, pred_seqs):
        ge, pe = entities(g), entities(p)
        tp += len(ge & pe)
        fp += len(pe - ge)
        fn += len(ge - pe)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return 2 * prec * rec / (prec + rec) if prec + rec else 0.0


def scores(rows, intent_pred, dept_pred, slot_pred):
    routed = [i for i, r in enumerate(rows) if r["department"] != "none"]
    return {
        "n": len(rows),
        "intent_acc": round(accuracy_score([r["intent"] for r in rows], intent_pred), 4),
        "intent_macro_f1": round(f1_score([r["intent"] for r in rows], intent_pred, average="macro"), 4),
        "dept_top1_acc": round(accuracy_score([rows[i]["department"] for i in routed],
                                              [dept_pred[i] for i in routed]), 4) if routed else None,
        "slot_entity_f1": round(entity_f1([r["tags"] for r in rows], slot_pred), 4),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="../data/sample")
    ap.add_argument("--out", default="../results/baseline")
    args = ap.parse_args()
    train = load(Path(args.data) / "train.jsonl") + load(Path(args.data) / "val.jsonl")
    tests = {"test": load(Path(args.data) / "test.jsonl")}
    if (Path(args.data) / "test_freeform.jsonl").exists():
        tests["freeform"] = load(Path(args.data) / "test_freeform.jsonl")

    intent_m = text_clf().fit([r["text"] for r in train], [r["intent"] for r in train])
    dtrain = [r for r in train if r["department"] != "none"]
    dept_m = text_clf().fit([r["text"] for r in dtrain], [r["department"] for r in dtrain])
    crf = sklearn_crfsuite.CRF(algorithm="lbfgs", c1=0.1, c2=0.1, max_iterations=150)
    crf.fit([[tok_features(r["tokens"], i) for i in range(len(r["tokens"]))] for r in train],
            [r["tags"] for r in train])

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    all_results = {}
    for name, test in tests.items():
        texts = [r["text"] for r in test]
        ip, dp = list(intent_m.predict(texts)), list(dept_m.predict(texts))
        sp = crf.predict([[tok_features(r["tokens"], i) for i in range(len(r["tokens"]))] for r in test])
        result = {"overall": scores(test, ip, dp, sp)}
        by_script = defaultdict(list)
        for i, r in enumerate(test):
            by_script[r["script"]].append(i)
        for s, idx in sorted(by_script.items()):
            result[s] = scores([test[i] for i in idx], [ip[i] for i in idx], [dp[i] for i in idx],
                               [sp[i] for i in idx])
        all_results[name] = result
        print(f"\n== {name} ==")
        print(f"{'split':8} {'n':>5} {'intent_acc':>11} {'intent_F1':>10} {'dept_acc':>9} {'slot_F1':>8}")
        for k, v in result.items():
            print(f"{k:8} {v['n']:>5} {v['intent_acc']:>11} {v['intent_macro_f1']:>10} "
                  f"{str(v['dept_top1_acc']):>9} {v['slot_entity_f1']:>8}")
    (out / "scores.json").write_text(json.dumps(all_results, indent=2))


if __name__ == "__main__":
    main()
