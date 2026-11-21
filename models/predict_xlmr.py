"""Load a trained joint XLM-R model and parse messages.

    python predict_xlmr.py --model_dir ../results/xlmr_final/model "mujhe kal Dr. Ayesha se milna hai"
    python predict_xlmr.py --model_dir ../results/xlmr_final/model      # interactive

Returns intent (+confidence), department (+confidence, only meaningful for routing intents)
and slot spans. This is the function the dialogue manager will call.
"""
import argparse
import io
import json
import re
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_xlmr import NONE_DEPT_ID, JointXLMR, entities, fix_bio  # noqa: E402
from transformers import AutoTokenizer  # noqa: E402

ROUTING_INTENTS = {"book_appointment", "describe_symptom", "doctor_availability"}


def simple_tokenize(text):
    # same rule as data_gen/generate.py TOKEN_RE, so MB-1042 and 3:30 stay one token
    return re.findall(r"\w+(?:[-:]\w+)*|[^\w\s]", text)


def load_weights(md):
    """joint_xlmr.pt (fp32), or joint_xlmr_fp16.pt.part0, part1, ... (fp16 split into <300 MB parts
    so the shared project folder can sync it). fp16 weights are cast back to fp32."""
    if (md / "joint_xlmr.pt").exists():
        return torch.load(md / "joint_xlmr.pt", map_location="cpu")
    parts = sorted(md.glob("joint_xlmr_fp16.pt.part*"), key=lambda p: int(p.name.rsplit("part", 1)[1]))
    if not parts:
        raise FileNotFoundError(f"no joint_xlmr.pt or joint_xlmr_fp16.pt.part* in {md}")
    sd = torch.load(io.BytesIO(b"".join(p.read_bytes() for p in parts)), map_location="cpu")
    return {k: v.float() if v.is_floating_point() else v for k, v in sd.items()}


class Parser:
    def __init__(self, model_dir, device=None):
        md = Path(model_dir)
        self.labels = json.loads((md / "labels.json").read_text())
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.tok = AutoTokenizer.from_pretrained(md)
        self.model = JointXLMR(self.labels["model"])
        self.model.load_state_dict(load_weights(md))
        self.model.to(self.device).eval()

    @torch.no_grad()
    def __call__(self, text):
        words = simple_tokenize(text)
        enc = self.tok([words], is_split_into_words=True, truncation=True,
                       max_length=self.labels["max_len"], return_tensors="pt")
        il, dl, sl = self.model(enc["input_ids"].to(self.device),
                                enc["attention_mask"].to(self.device))
        ip = il.softmax(-1)[0]
        dl = dl.clone()
        dl[:, NONE_DEPT_ID] = -1e9
        dp = dl.softmax(-1)[0]
        first, prev = [], None
        for pos, w in enumerate(enc.word_ids(0)):
            if w is not None and w != prev:
                first.append(pos)
            prev = w
        sarg = sl.argmax(-1)[0].tolist()
        tags = fix_bio([self.labels["tags"][str(sarg[p])] for p in first]
                       + ["O"] * (len(words) - len(first)))
        intent = self.labels["intents"][str(int(ip.argmax()))]
        out = {"text": text, "intent": intent, "intent_conf": round(float(ip.max()), 3),
               "slots": [{"label": lab, "value": " ".join(words[s:e])}
                         for lab, s, e in sorted(entities(tags), key=lambda x: x[1])]}
        if intent in ROUTING_INTENTS:
            out["department"] = self.labels["departments"][str(int(dp.argmax()))]
            out["department_conf"] = round(float(dp.max()), 3)
        return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model_dir", default="../results/xlmr_final/model")
    ap.add_argument("text", nargs="*")
    a = ap.parse_args()
    p = Parser(a.model_dir)
    if a.text:
        print(json.dumps(p(" ".join(a.text)), ensure_ascii=False, indent=2))
    else:
        while True:
            try:
                t = input("> ")
            except EOFError:
                break
            print(json.dumps(p(t), ensure_ascii=False, indent=2))
