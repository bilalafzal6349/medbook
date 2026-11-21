"""Joint XLM-R model for MedBook NLU: one encoder, three heads.

    intent      14 classes, from the <s> (CLS) vector, class-weighted loss
    department   9 classes (8 departments + none), from the <s> vector
    slots       19 BIO tags, one per word (first sub-word of each word)

Usage (GPU, e.g. Colab T4, about 10 minutes):
    pip install torch transformers sentencepiece scikit-learn
    python train_xlmr.py --data ../data/dataset_v1 --out ../results/xlmr_v1

Small CPU run (no GPU):
    python train_xlmr.py --epochs 3 --max_train 3000 --batch_size 16

Scores are computed exactly like baseline.py, so the two tables can be compared directly.
Outputs in --out: scores.json, errors_freeform.jsonl, train_log.json, and model/ (best checkpoint
on val) unless --no_save.
"""
import argparse
import json
import math
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import accuracy_score, f1_score
from transformers import AutoModel, AutoTokenizer, get_linear_schedule_with_warmup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "data_gen"))
from schema import DEPT2ID, INTENT2ID, NO_DEPARTMENT, TAG2ID  # noqa: E402

ID2INTENT = {v: k for k, v in INTENT2ID.items()}
ID2TAG = {v: k for k, v in TAG2ID.items()}
ID2DEPT = {v: k for k, v in DEPT2ID.items()}
NONE_DEPT_ID = DEPT2ID[NO_DEPARTMENT]


# ----------------------------------------------------------------------------- data

def load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8")]


def encode(rows, tok, max_len):
    """Tokenise pre-split words; label only the first sub-word of each word (others -100)."""
    enc = tok([r["tokens"] for r in rows], is_split_into_words=True, truncation=True,
              max_length=max_len)
    feats = []
    for i, r in enumerate(rows):
        word_ids = enc.word_ids(i)
        slot_lab, first_idx, prev = [], [], None
        for pos, w in enumerate(word_ids):
            if w is None or w == prev:
                slot_lab.append(-100)
            else:
                slot_lab.append(TAG2ID[r["tags"][w]])
                first_idx.append(pos)
            prev = w
        feats.append({
            "input_ids": enc["input_ids"][i],
            "slot_labels": slot_lab,
            "first_idx": first_idx,          # used at decode time to map back to words
            "n_words": len(r["tokens"]),
            "intent": INTENT2ID[r["intent"]],
            "dept": DEPT2ID[r["department"]],
        })
    return feats


def collate(batch, pad_id):
    L = max(len(f["input_ids"]) for f in batch)
    ids = torch.full((len(batch), L), pad_id, dtype=torch.long)
    att = torch.zeros((len(batch), L), dtype=torch.long)
    slots = torch.full((len(batch), L), -100, dtype=torch.long)
    for i, f in enumerate(batch):
        n = len(f["input_ids"])
        ids[i, :n] = torch.tensor(f["input_ids"])
        att[i, :n] = 1
        slots[i, :n] = torch.tensor(f["slot_labels"])
    return {"input_ids": ids, "attention_mask": att, "slot_labels": slots,
            "intent": torch.tensor([f["intent"] for f in batch]),
            "dept": torch.tensor([f["dept"] for f in batch])}


def batches(feats, bs, shuffle, pad_id):
    idx = list(range(len(feats)))
    if shuffle:
        random.shuffle(idx)
    for s in range(0, len(idx), bs):
        yield [feats[j] for j in idx[s:s + bs]], collate([feats[j] for j in idx[s:s + bs]], pad_id)


# ----------------------------------------------------------------------------- model

class JointXLMR(nn.Module):
    def __init__(self, name, dropout=0.1):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(name)
        h = self.encoder.config.hidden_size
        self.drop = nn.Dropout(dropout)
        self.intent_head = nn.Sequential(nn.Linear(h, h), nn.Tanh(), nn.Dropout(dropout),
                                         nn.Linear(h, len(INTENT2ID)))
        self.dept_head = nn.Sequential(nn.Linear(h, h), nn.Tanh(), nn.Dropout(dropout),
                                       nn.Linear(h, len(DEPT2ID)))
        self.slot_head = nn.Linear(h, len(TAG2ID))

    def forward(self, input_ids, attention_mask):
        seq = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        cls = self.drop(seq[:, 0])
        return self.intent_head(cls), self.dept_head(cls), self.slot_head(self.drop(seq))


def intent_class_weights(rows, power):
    """(max_count / count) ** power. power=0.5 lifts greet/goodbye (14-16 rows) about 10x."""
    c = Counter(r["intent"] for r in rows)
    mx = max(c.values())
    w = [(mx / max(c.get(ID2INTENT[i], 1), 1)) ** power for i in range(len(INTENT2ID))]
    return torch.tensor(w, dtype=torch.float)


# ----------------------------------------------------------------------------- metrics (same as baseline.py)

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


def fix_bio(tags):
    """Turn an I-X that does not follow B-X/I-X into B-X, so spans are well formed."""
    out = []
    for t in tags:
        if t.startswith("I-") and (not out or out[-1][2:] != t[2:]):
            t = "B-" + t[2:]
        out.append(t)
    return out


# ----------------------------------------------------------------------------- predict / evaluate

@torch.no_grad()
def predict(model, feats, bs, pad_id, device):
    model.eval()
    ip, dp, dconf, sp = [], [], [], []
    for fb, b in batches(feats, bs, False, pad_id):
        il, dl, sl = model(b["input_ids"].to(device), b["attention_mask"].to(device))
        ip += [ID2INTENT[i] for i in il.argmax(-1).tolist()]
        # department = best real department (never "none"), as the router always needs one
        dl = dl.clone()
        dl[:, NONE_DEPT_ID] = -1e9
        prob = dl.softmax(-1)
        conf, arg = prob.max(-1)
        dp += [ID2DEPT[i] for i in arg.tolist()]
        dconf += conf.tolist()
        sarg = sl.argmax(-1).tolist()
        for f, row in zip(fb, sarg):
            tags = [ID2TAG[row[p]] for p in f["first_idx"]]
            tags += ["O"] * (f["n_words"] - len(tags))  # words cut by max_len
            sp.append(fix_bio(tags))
    return ip, dp, dconf, sp


def evaluate(rows, preds):
    ip, dp, _, sp = preds
    result = {"overall": scores(rows, ip, dp, sp)}
    by_script = defaultdict(list)
    for i, r in enumerate(rows):
        by_script[r["script"]].append(i)
    for s, idx in sorted(by_script.items()):
        result[s] = scores([rows[i] for i in idx], [ip[i] for i in idx], [dp[i] for i in idx],
                           [sp[i] for i in idx])
    return result


def print_table(name, result):
    print(f"\n== {name} ==")
    print(f"{'split':8} {'n':>5} {'intent_acc':>11} {'intent_F1':>10} {'dept_acc':>9} {'slot_F1':>8}")
    for k, v in result.items():
        print(f"{k:8} {v['n']:>5} {v['intent_acc']:>11} {v['intent_macro_f1']:>10} "
              f"{str(v['dept_top1_acc']):>9} {v['slot_entity_f1']:>8}")


# ----------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="../data/dataset_v1")
    ap.add_argument("--out", default="../results/xlmr_v1")
    ap.add_argument("--model", default="xlm-roberta-base")
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--batch_size", type=int, default=32)
    ap.add_argument("--lr", type=float, default=3e-5, help="encoder learning rate")
    ap.add_argument("--head_lr", type=float, default=1e-3)
    ap.add_argument("--max_len", type=int, default=64)
    ap.add_argument("--class_weight_power", type=float, default=0.5)
    ap.add_argument("--slot_loss_weight", type=float, default=1.0)
    ap.add_argument("--dept_loss_weight", type=float, default=1.0)
    ap.add_argument("--dept_routed_only", type=int, default=1,
                    help="1: train the department head only on rows whose department is not none")
    ap.add_argument("--max_train", type=int, default=0, help="subsample train rows (CPU runs)")
    ap.add_argument("--train_on_val", action="store_true",
                    help="add val to train after choosing epochs (final model only)")
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--no_save", action="store_true")
    args = ap.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print("device:", device, flush=True)

    data = Path(args.data)
    train, val = load(data / "train.jsonl"), load(data / "val.jsonl")
    tests = {"test": load(data / "test.jsonl")}
    if (data / "test_freeform.jsonl").exists():
        tests["freeform"] = load(data / "test_freeform.jsonl")
    if args.max_train and args.max_train < len(train):
        # keep every greet/goodbye row, subsample the rest
        rare = [r for r in train if r["intent"] in ("greet", "goodbye")]
        rest = [r for r in train if r["intent"] not in ("greet", "goodbye")]
        random.shuffle(rest)
        train = rare + rest[:args.max_train - len(rare)]
    if args.train_on_val:
        train = train + val
    print(f"train {len(train)}  val {len(val)}  " +
          "  ".join(f"{k} {len(v)}" for k, v in tests.items()), flush=True)

    tok = AutoTokenizer.from_pretrained(args.model)
    pad_id = tok.pad_token_id
    ftrain = encode(train, tok, args.max_len)
    fval = encode(val, tok, args.max_len)
    ftests = {k: encode(v, tok, args.max_len) for k, v in tests.items()}

    model = JointXLMR(args.model).to(device)
    enc_params = [p for n, p in model.named_parameters() if n.startswith("encoder.")]
    head_params = [p for n, p in model.named_parameters() if not n.startswith("encoder.")]
    opt = torch.optim.AdamW([{"params": enc_params, "lr": args.lr},
                             {"params": head_params, "lr": args.head_lr}], weight_decay=0.01)
    steps = args.epochs * math.ceil(len(ftrain) / args.batch_size)
    sched = get_linear_schedule_with_warmup(opt, int(0.1 * steps), steps)

    w = intent_class_weights(train, args.class_weight_power).to(device)
    print("intent weights:", {ID2INTENT[i]: round(x, 2) for i, x in enumerate(w.tolist())})
    ce_intent = nn.CrossEntropyLoss(weight=w)
    # department loss only on rows that carry a routing signal (as in baseline.py);
    # "none" rows (63% of train) otherwise swamp the 8 real departments
    ce_dept = nn.CrossEntropyLoss(ignore_index=NONE_DEPT_ID if args.dept_routed_only else -100)
    ce_slot = nn.CrossEntropyLoss(ignore_index=-100)
    use_amp = device == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    log, best, best_state = [], -1.0, None
    t0 = time.time()
    for ep in range(1, args.epochs + 1):
        model.train()
        tot, n = 0.0, 0
        for step, (_, b) in enumerate(batches(ftrain, args.batch_size, True, pad_id)):
            b = {k: v.to(device) for k, v in b.items()}
            with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=use_amp):
                il, dl, sl = model(b["input_ids"], b["attention_mask"])
                dloss = ce_dept(dl.float(), b["dept"]) if (b["dept"] != ce_dept.ignore_index).any() \
                    else dl.sum() * 0.0
                loss = (ce_intent(il.float(), b["intent"])
                        + args.dept_loss_weight * dloss
                        + args.slot_loss_weight * ce_slot(sl.float().reshape(-1, sl.size(-1)),
                                                          b["slot_labels"].reshape(-1)))
            opt.zero_grad()
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(opt)
            scaler.update()
            sched.step()
            tot += loss.item()
            n += 1
            if step % 50 == 0:
                print(f"  ep {ep} step {step} loss {tot / n:.4f}  {time.time() - t0:.0f}s", flush=True)
        vres = evaluate(val, predict(model, fval, 64, pad_id, device))["overall"]
        # model selection on val (unseen templates): mean of intent macro-F1, slot F1, dept acc
        sel = (vres["intent_macro_f1"] + vres["slot_entity_f1"] + vres["dept_top1_acc"]) / 3
        log.append({"epoch": ep, "train_loss": round(tot / n, 4), "val": vres,
                    "minutes": round((time.time() - t0) / 60, 1)})
        print(f"epoch {ep}: loss {tot / n:.4f}  val {vres}", flush=True)
        # with --train_on_val, val is no longer held out, so keep the last epoch instead
        if sel > best or args.train_on_val:
            best = sel
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            print("  new best on val", flush=True)

    model.load_state_dict(best_state)
    all_results = {"config": vars(args), "best_val_selection_score": round(best, 4)}
    for name, rows in tests.items():
        preds = predict(model, ftests[name], 64, pad_id, device)
        res = evaluate(rows, preds)
        all_results[name] = res
        print_table(name, res)
        if name == "freeform":
            with open(out / "errors_freeform.jsonl", "w", encoding="utf-8") as f:
                for r, i, d, c, s in zip(rows, *preds):
                    bad_dept = r["department"] != "none" and d != r["department"]
                    if i != r["intent"] or s != r["tags"] or bad_dept:
                        f.write(json.dumps({
                            "text": r["text"], "script": r["script"],
                            "intent": r["intent"], "pred_intent": i,
                            "department": r["department"], "pred_department": d,
                            "dept_conf": round(c, 3),
                            "gold_spans": sorted(entities(r["tags"])),
                            "pred_spans": sorted(entities(s)),
                        }, ensure_ascii=False) + "\n")
    (out / "scores.json").write_text(json.dumps(all_results, indent=2))
    (out / "train_log.json").write_text(json.dumps(log, indent=2))
    if not args.no_save:
        md = out / "model"
        md.mkdir(exist_ok=True)
        torch.save(model.state_dict(), md / "joint_xlmr.pt")
        tok.save_pretrained(md)
        (md / "labels.json").write_text(json.dumps(
            {"model": args.model, "max_len": args.max_len, "intents": ID2INTENT,
             "tags": ID2TAG, "departments": ID2DEPT}, indent=2))
        print("saved model to", md)
    print(f"total time {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
