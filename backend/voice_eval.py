"""Speech recognition evaluation for MedBook voice input.

    python voice_eval.py --build                    # make the synthetic clinic clips (data/voice_eval_v1/)
    python voice_eval.py --set synthetic --models tiny base small medium large-v3-turbo
    python voice_eval.py --set fleurs --n 100       # real read Urdu speech (Google FLEURS ur_pk test)
    python voice_eval.py --set recordings --dir my_clips/   # your own recordings (see below)

Three test sets
    synthetic   150 Urdu-script clinic messages (42 free-form + 108 held-out test templates) spoken by
                Meta MMS-TTS, clean and with noise at 10 dB SNR. Labelled, so we also score what matters:
                does the NLU still get the intent and the department from the transcript?
    fleurs      Real people reading Wikipedia sentences in Urdu. General Urdu WER, not clinic language.
    recordings  A folder of audio files plus refs.tsv: `file<TAB>text[<TAB>intent<TAB>department]`.
                Record yourself, classmates and family saying clinic requests; this is the honest test.

Metrics: WER and CER after normalising (punctuation, diacritics, Arabic/Urdu letter variants, digits written
as words), real-time factor (processing time / audio length, on this machine's CPU), and for labelled sets
intent accuracy and department accuracy of the NLU on the transcript next to the same NLU on the typed text.
Results go to ../results/voice_eval/<set>.json
"""
import argparse
import json
import random
import re
import sys
import tarfile
import tempfile
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import voice  # noqa: E402

SYN_DIR = ROOT / "data" / "voice_eval_v1"
OUT_DIR = ROOT / "results" / "voice_eval"
FLEURS = "https://huggingface.co/datasets/google/fleurs/resolve/main/data/ur_pk"


def dataset_dir():
    for name in ("dataset_v2", "dataset_v1"):
        d = ROOT / "data" / name
        if (d / "test_freeform.jsonl").exists():
            return d
    raise SystemExit("no dataset found")


# ----------------------------------------------------------------------------- normalisation + WER
PUNCT_RE = re.compile(r"[\"'“”‘’«»()\[\]{}.,،؛;:!?؟۔\-–—_/\\*…]")
DIACRITICS_RE = re.compile(r"[ً-ٰٟؐ-ؚ]")
LETTERS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ه": "ہ", "ۀ": "ہ", "ة": "ہ", "أ": "ا", "إ": "ا",
                         "ٱ": "ا", "ۓ": "ے", "ؤ": "و", "ئ": "ئ"})


def norm(text):
    t = text.translate(voice.URDU_DIGITS).translate(LETTERS)
    t = DIACRITICS_RE.sub("", t).replace("آ", "آ")
    t = re.sub(r"\d+", lambda m: " " + voice.number_words(int(m.group(0))) + " ", t)
    t = PUNCT_RE.sub(" ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


class Rate:
    def __init__(self):
        self.err = self.n = 0

    def add(self, ref, hyp):
        self.err += edit_distance(ref, hyp)
        self.n += len(ref)

    @property
    def value(self):
        return round(self.err / max(1, self.n), 4)


# ----------------------------------------------------------------------------- test sets
def build_synthetic(seed=13):
    """Speak 150 held-out Urdu-script messages with MMS-TTS. Speaking rate and VITS noise vary per clip."""
    import numpy as np
    import soundfile as sf
    import torch
    d = dataset_dir()
    rng = random.Random(seed)
    urdu = lambda f: [r for r in (json.loads(l) for l in open(d / f, encoding="utf-8"))  # noqa: E731
                      if r["script"] == "urdu" and not re.search("[A-Za-z]", r["text"])]
    free = urdu("test_freeform.jsonl")
    test = urdu("test.jsonl")
    by_intent = defaultdict(list)
    for r in test:
        by_intent[r["intent"]].append(r)
    picked, k = [], 150 - len(free)
    while len(picked) < k:                       # round-robin over intents so rare ones are in
        for it in sorted(by_intent):
            if by_intent[it] and len(picked) < k:
                picked.append(by_intent[it].pop(rng.randrange(len(by_intent[it]))))
    model, tok = voice.get_tts()
    sr = model.config.sampling_rate
    SYN_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, r in enumerate(free + picked):
        torch.manual_seed(seed + i)
        model.speaking_rate = rng.uniform(0.9, 1.15)
        with torch.no_grad():
            wav = model(**tok(voice.speakable(r["text"]), return_tensors="pt")).waveform[0].numpy()  # digits as words
        wav = np.concatenate([np.zeros(int(0.3 * sr)), wav, np.zeros(int(0.3 * sr))]).astype(np.float32)
        name = f"syn_{i:03d}.wav"
        sf.write(SYN_DIR / name, wav, sr, subtype="PCM_16")
        rows.append({"file": name, "text": r["text"], "intent": r["intent"], "department": r["department"],
                     "source": "freeform" if r["source"] == "freeform" else "template", "id": r["id"]})
    model.speaking_rate = 1.0
    with open(SYN_DIR / "refs.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} clips to {SYN_DIR}")


def add_noise(path, snr_db, seed):
    """Mix in pink-ish noise at the given SNR (a fan, a street, a cheap mic)."""
    import numpy as np
    import soundfile as sf
    wav, sr = sf.read(path, dtype="float32")
    rng = np.random.default_rng(seed)
    white = rng.standard_normal(len(wav)).astype(np.float32)
    pink = np.convolve(white, np.ones(8) / 8, mode="same")         # low-passed: more like room noise
    sig = wav[np.abs(wav) > 1e-4]
    p_sig = float(np.mean(sig ** 2)) if len(sig) else 1e-6
    pink *= np.sqrt(p_sig / (10 ** (snr_db / 10)) / float(np.mean(pink ** 2)))
    out = Path(tempfile.mkdtemp()) / Path(path).name
    sf.write(out, np.clip(wav + pink, -1, 1), sr, subtype="PCM_16")
    return str(out)


def load_set(name, n, directory):
    if name == "synthetic":
        if not (SYN_DIR / "refs.jsonl").exists():
            build_synthetic()
        rows = [json.loads(l) for l in open(SYN_DIR / "refs.jsonl", encoding="utf-8")]
        return [dict(r, path=str(SYN_DIR / r["file"])) for r in rows]
    if name == "fleurs":
        cache = Path(tempfile.gettempdir()) / "medbook_fleurs"
        cache.mkdir(exist_ok=True)
        for f in ("test.tsv", "audio/test.tar.gz"):
            dst = cache / Path(f).name
            if not dst.exists():
                print("downloading", f)
                urllib.request.urlretrieve(f"{FLEURS}/{f}", dst)
        refs = {}
        for line in open(cache / "test.tsv", encoding="utf-8"):
            p = line.rstrip("\n").split("\t")
            refs[p[1]] = p[2]                                     # raw transcription, with punctuation
        names = sorted(refs)
        random.Random(13).shuffle(names)
        names = set(names[:n])
        with tarfile.open(cache / "test.tar.gz") as tar:
            for m in tar.getmembers():
                base = Path(m.name).name
                if base in names and not (cache / base).exists():
                    with open(cache / base, "wb") as f:
                        f.write(tar.extractfile(m).read())
        return [{"file": b, "text": refs[b], "path": str(cache / b)} for b in sorted(names)]
    if name == "recordings":
        d = Path(directory)
        rows = []
        for line in open(d / "refs.tsv", encoding="utf-8"):
            p = line.rstrip("\n").split("\t")
            if len(p) >= 2 and not line.startswith("#"):
                rows.append({"file": p[0], "text": p[1], "path": str(d / p[0]),
                             **({"intent": p[2]} if len(p) > 2 and p[2] else {}),
                             **({"department": p[3]} if len(p) > 3 and p[3] else {})})
        return rows
    raise SystemExit(f"unknown set {name}")


# ----------------------------------------------------------------------------- NLU on transcripts
class NLUScorer:
    def __init__(self):
        from clinic_db import Clinic
        from nlu import NLU
        self.clinic = Clinic(Path(tempfile.mkdtemp()) / "v.db")
        self.nlu = NLU(self.clinic.doctors())

    def __call__(self, text):
        """(intent, department) the way the dialogue manager would decide them."""
        from dialogue import department_from_name
        from routing import route
        if not text:
            return "none", "none"
        p = self.nlu.parse(text)
        slots = {s["label"]: s["value"] for s in p["slots"]}
        if p["rules"].get("doctor_id"):
            dept = self.clinic.doctor(p["rules"]["doctor_id"])["department"]
        elif "DEPARTMENT" in slots and department_from_name(slots["DEPARTMENT"]):
            dept = department_from_name(slots["DEPARTMENT"])
        else:
            md, mc = (p["department"], p["department_conf"]) if p.get("department") else self.nlu.department_of(text)
            dept = route(text, md, mc)[0]
        return p["intent"], dept


# ----------------------------------------------------------------------------- main loop
def evaluate(rows, model, prompt, noise, scorer):
    wer, cer, nlu = Rate(), Rate(), Counter()
    audio_s = proc_s = 0.0
    samples = []
    for i, r in enumerate(rows):
        path = add_noise(r["path"], noise, i) if noise is not None else r["path"]
        t = time.time()
        text, raw, info = voice.transcribe(path, size=model, prompt=prompt)
        proc_s += time.time() - t
        audio_s += info["audio_s"]
        ref, hyp = norm(r["text"]), norm(text)
        wer.add(ref.split(), hyp.split())
        cer.add(ref.replace(" ", ""), hyp.replace(" ", ""))
        row = {"file": r["file"], "ref": r["text"], "hyp": text}
        if scorer and "intent" in r:
            it_ref, dp_ref = scorer.ref_cache.setdefault(r["file"], scorer(r["text"]))
            it_hyp, dp_hyp = scorer(text)
            nlu["n"] += 1
            nlu["intent_gold_text"] += it_ref == r["intent"]
            nlu["intent_gold_voice"] += it_hyp == r["intent"]
            nlu["intent_same"] += it_hyp == it_ref
            if r.get("department", "none") != "none":
                nlu["dept_n"] += 1
                nlu["dept_gold_text"] += dp_ref == r["department"]
                nlu["dept_gold_voice"] += dp_hyp == r["department"]
            if r["intent"] == "emergency":
                nlu["emerg_n"] += 1
                nlu["emerg_voice"] += it_hyp == "emergency"
            row.update(intent=r["intent"], intent_voice=it_hyp)
        samples.append(row)
    res = {"model": model, "prompt": ("clinic+doctors" if voice._vocab else "clinic") if prompt else False, "noise_snr_db": noise, "n": len(rows),
           "wer": wer.value, "cer": cer.value, "rtf": round(proc_s / max(audio_s, 1e-6), 3),
           "sec_per_clip": round(proc_s / len(rows), 2)}
    if nlu["n"]:
        res.update(intent_acc_typed=round(nlu["intent_gold_text"] / nlu["n"], 3),
                   intent_acc_voice=round(nlu["intent_gold_voice"] / nlu["n"], 3),
                   intent_same_as_typed=round(nlu["intent_same"] / nlu["n"], 3))
        if nlu["dept_n"]:
            res.update(dept_n=nlu["dept_n"], dept_acc_typed=round(nlu["dept_gold_text"] / nlu["dept_n"], 3),
                       dept_acc_voice=round(nlu["dept_gold_voice"] / nlu["dept_n"], 3))
        if nlu["emerg_n"]:
            res.update(emergency_recall_voice=f"{nlu['emerg_voice']}/{nlu['emerg_n']}")
    return res, samples


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--set", default="synthetic", choices=["synthetic", "fleurs", "recordings"])
    ap.add_argument("--dir", help="folder for --set recordings")
    ap.add_argument("--models", nargs="+", default=["small"])
    ap.add_argument("--n", type=int, default=100, help="FLEURS clips")
    ap.add_argument("--noise", nargs="+", default=None, help="SNRs in dB; 'clean' for none (synthetic default: clean 10)")
    ap.add_argument("--prompt", choices=["on", "off", "both"], default="on")
    ap.add_argument("--no_nlu", action="store_true")
    ap.add_argument("--doctors", action="store_true", help="add doctor names to the prompt, as the app does")
    a = ap.parse_args()
    if a.build:
        build_synthetic()
        return
    rows = load_set(a.set, a.n, a.dir)
    if a.doctors:
        import sys as _s
        _s.path.insert(0, str(ROOT / "data_gen"))
        from lexicons import DOCTORS
        voice.set_vocabulary([d["urdu"] for d, _ in DOCTORS])
    noises = a.noise or (["clean", "10"] if a.set == "synthetic" else ["clean"])
    noises = [None if x == "clean" else float(x) for x in noises]
    prompts = {"on": [True], "off": [False], "both": [False, True]}[a.prompt]
    scorer = None
    if not a.no_nlu and any("intent" in r for r in rows):
        scorer = NLUScorer()
        scorer.ref_cache = {}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{a.set}.json"
    results = json.loads(out_path.read_text()) if out_path.exists() else {"runs": []}
    for model in a.models:
        for prompt in prompts:
            for noise in noises:
                res, samples = evaluate(rows, model, prompt, noise, scorer)
                if scorer:
                    res["nlu_engine"] = scorer.nlu.engine_name
                print(json.dumps(res, ensure_ascii=False), flush=True)
                key = (res["model"], res["prompt"], res["noise_snr_db"])
                results["runs"] = [r for r in results["runs"]
                                   if (r["model"], r["prompt"], r["noise_snr_db"]) != key] + [res]
                tag = f"{model}_{('prompt_doctors' if voice._vocab else 'prompt') if prompt else 'noprompt'}_{'clean' if noise is None else f'snr{int(noise)}'}"
                with open(OUT_DIR / f"{a.set}_{tag}_transcripts.jsonl", "w", encoding="utf-8") as f:
                    for s in samples:
                        f.write(json.dumps(s, ensure_ascii=False) + "\n")
                out_path.write_text(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
