"""Score the baseline (TF-IDF + LR, CRF) and the fine-tuned XLM-R on exactly the same messages
as llm_eval.py, one message at a time, with per-message latency on this machine.

    pip install torch transformers sentencepiece scikit-learn sklearn-crfsuite
    python local_eval.py --out ../results/llm_compare/local --model_dir ../results/xlmr_final/model

Writes <out>/baseline/scores.json and <out>/xlmr/scores.json in the same format as llm_eval.py.
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from llm_eval import load, score_by_script, test_sample  # noqa: E402


def runtime(lat):
    s = sorted(lat)
    return {"latency_mean_s": round(statistics.mean(lat), 4), "latency_median_s": round(statistics.median(lat), 4),
            "latency_p95_s": round(s[int(0.95 * (len(s) - 1))], 4), "usd_per_message": 0.0,
            "usd_per_1k_messages": 0.0}


def baseline_predictor(data):
    import sklearn_crfsuite
    from baseline import text_clf, tok_features
    train = load(data / "train.jsonl") + load(data / "val.jsonl")
    intent_m = text_clf().fit([r["text"] for r in train], [r["intent"] for r in train])
    dtrain = [r for r in train if r["department"] != "none"]
    dept_m = text_clf().fit([r["text"] for r in dtrain], [r["department"] for r in dtrain])
    crf = sklearn_crfsuite.CRF(algorithm="lbfgs", c1=0.1, c2=0.1, max_iterations=150)
    crf.fit([[tok_features(r["tokens"], i) for i in range(len(r["tokens"]))] for r in train],
            [r["tags"] for r in train])

    def predict(r):
        return {"intent": intent_m.predict([r["text"]])[0], "department": dept_m.predict([r["text"]])[0],
                "slots": [], "tagged": {"tags": crf.predict_single(
                    [tok_features(r["tokens"], i) for i in range(len(r["tokens"]))])}}
    return predict


def xlmr_predictor(model_dir):
    import torch
    from predict_xlmr import Parser
    from train_xlmr import NONE_DEPT_ID, fix_bio
    torch.set_num_threads(max(1, torch.get_num_threads()))
    p = Parser(model_dir, device="cpu")

    @torch.no_grad()
    def predict(r):
        words = r["tokens"]  # gold tokenisation, as in train_xlmr.py scoring
        enc = p.tok([words], is_split_into_words=True, truncation=True, max_length=p.labels["max_len"],
                    return_tensors="pt")
        il, dl, sl = p.model(enc["input_ids"], enc["attention_mask"])
        dl = dl.clone()
        dl[:, NONE_DEPT_ID] = -1e9
        first, prev = [], None
        for pos, w in enumerate(enc.word_ids(0)):
            if w is not None and w != prev:
                first.append(pos)
            prev = w
        sarg = sl.argmax(-1)[0].tolist()
        tags = fix_bio([p.labels["tags"][str(sarg[q])] for q in first] + ["O"] * (len(words) - len(first)))
        return {"intent": p.labels["intents"][str(int(il.argmax()))],
                "department": p.labels["departments"][str(int(dl.argmax()))],
                "slots": [], "tagged": {"tags": tags}}
    return predict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(HERE.parent / "data" / "dataset_v1"))
    ap.add_argument("--model_dir", default=str(HERE.parent / "results" / "xlmr_final" / "model"))
    ap.add_argument("--test_n", type=int, default=300)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", choices=["baseline", "xlmr"])
    a = ap.parse_args()
    data = Path(a.data)
    sets = {"test": test_sample(load(data / "test.jsonl"), a.test_n), "freeform": load(data / "test_freeform.jsonl")}
    makers = {"baseline": lambda: baseline_predictor(data), "xlmr": lambda: xlmr_predictor(a.model_dir)}
    for name, make in makers.items():
        if a.only and name != a.only:
            continue
        predict = make()
        predict(sets["freeform"][0])  # warm-up, not timed
        results = {}
        for sname, rows in sets.items():
            preds, lat = [], []
            for r in rows:
                t0 = time.perf_counter()
                preds.append(predict(r))
                lat.append(time.perf_counter() - t0)
            results[sname] = score_by_script(rows, preds)
            results[sname]["runtime"] = runtime(lat)
            print(name, sname, json.dumps(results[sname]["overall"]), json.dumps(results[sname]["runtime"]))
        out = Path(a.out) / name
        out.mkdir(parents=True, exist_ok=True)
        (out / "scores.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
