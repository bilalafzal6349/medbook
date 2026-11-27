# MedBook dataset v2

> **Chatbot demo** (FastAPI backend, dialogue manager, SQLite schedule, Next.js UI, optional Whisper voice):
> see [`DEMO.md`](DEMO.md) for how to run it, the mid-evaluation script and the dialogue-level results.
> **LLM mode**: set `ANTHROPIC_API_KEY` and an LLM runs the conversation with tool calls to the clinic database,
> with XLM-R hints and code-level safety guards (`backend/llm_agent.py`, see `DEMO.md`). Without a key the rule-based manager runs.
> **Deployment** (PostgreSQL, Redis sessions, Docker Compose, SMS reminders, staff schedule page, load test): see [`DEPLOY.md`](DEPLOY.md).

Code-switched Urdu/English clinic messages, labelled for intent, slots (BIO) and department.
Three writing styles throughout: Roman Urdu, Urdu script, and Urdu script mixed with English.

## What changed in v2 (label fixes)

v1 had three kinds of wrong department labels, found by a rule audit (`data_gen/audit_labels.py`) and by reading
300 random rows by hand:

| Slip in v1 | v1 rows (train / test) | v2 rule |
| --- | --- | --- |
| Child word with an adult age ("mere chote bhai ki umar 45 saal") labelled pediatrics | 48 / 26 | Pediatrics only for an age of 12 or under, or a child word with no age (same rule as `backend/routing.py`). Over 12, the symptom's adult department |
| Male patient sent to gynecology ("abbu ko periods band hai", "Muhammad Usman with Dr Farah Naz") | 25 / 2 | Templates about a man never draw gynecology, and gynecology bookings use female names |
| Two ages in one sentence ("mere 3 saal ke bete ki umar 35 years") | 5 / 0 | A child phrase that carries its own age is not used when the template has an AGE slot |

v2 also drops wrapper repeats ("ji ji haan", "Zuhr ke baad ke baad") and adds ages near the cut-off (10, 14, 15, 18) so the
model sees the boundary. The audit finds 0 slips in v2 (`python audit_labels.py ../data/dataset_v2`); the hand-read
sample had no other label errors. v1 is kept in `data/dataset_v1/` for comparison.

The backend keyword router had a matching bug: `نگل` (swallow) matched inside `منگل` (Tuesday), so any Urdu message
saying Tuesday was routed to ENT. That and similar substring hits (`early`, `دماغ`, `وکیل`) are fixed and covered by
`backend/tests/test_routing.py`.

## What is in `data/dataset_v2/`

| File | Rows | What it is |
| --- | --- | --- |
| `train.jsonl` | 6,238 | Template-generated, 319 templates |
| `val.jsonl` | 924 | 46 templates never seen in train |
| `test.jsonl` | 1,453 | 69 templates never seen in train or val |
| `test_freeform.jsonl` | 145 | Written one by one, not from templates. Test only |
| `dialogues.jsonl` | 600 dialogues | 3,319 labelled user turns, 11.3 turns on average, with belief state after every user turn |
| `stats.json` | | Counts by intent, script, department, slot and source |
| `samples.md` | | 30 random rows and one full dialogue to read |

- **Total:** 8,615 single-turn rows from 434 templates, plus 145 free-form rows and 600 dialogues.
- **Scripts:** 3,933 Roman, 2,536 Urdu, 2,146 mixed.
- **Labels:** 14 intents, 9 slot types and 8 departments (see `data_gen/schema.py`).
- **Variety sources:** 434 templates, expanded lexicons (40 names, 16 doctors, 9 to 15 symptoms per department), greeting and politeness wrappers, and Roman spelling noise on 25% of Roman rows.
- **Checks:** every span matches its text, tokens and tags align, and no test sentence appears in train.

## Row format

```json
{"id": "boo_r01-0000", "text": "Dr. Tariq Mehmood ka appointment book kar dein kal ke liye",
 "tokens": ["Dr", ".", "Tariq", "Mehmood", "ka", "appointment", "book", "kar", "dein", "kal", "ke", "liye"],
 "tags": ["B-DOCTOR", "I-DOCTOR", "I-DOCTOR", "I-DOCTOR", "O", "O", "O", "O", "O", "B-DATE", "O", "O"],
 "spans": [{"start": 0, "end": 17, "label": "DOCTOR", "value": "Dr. Tariq Mehmood"}, ...],
 "intent": "book_appointment", "department": "ent", "script": "roman",
 "style": "roman", "source": "template", "template_id": "boo_r01"}
```

`department` is set only for book_appointment, describe_symptom and doctor_availability, and is `none` otherwise.
`source` is template, noise or freeform.

## Baseline results (TF-IDF + logistic regression, CRF for slots)

| Test set | Intent accuracy | Intent macro-F1 | Department accuracy | Slot F1 |
| --- | --- | --- | --- | --- |
| v0 sample, unseen templates | 0.32 | 0.22 | 0.99 | 0.91 |
| v1, unseen templates | 0.71 | 0.69 | 1.00 | 0.93 |
| v1, free-form | 0.66 | 0.66 | 0.91 | 0.69 |
| v2, unseen templates | 0.69 | 0.67 | 0.94 | 0.92 |
| v2, free-form | 0.67 | 0.66 | 0.93 | 0.69 |

The free-form set is the hardest and most honest test. XLM-R fine-tuning should be compared against this line.
Results by script are in `results/baseline_v1/scores.json` and `results/baseline_v2/scores.json`.
The baseline's department score on v2 unseen templates drops from 1.00 to 0.94 because v2 asks it to read the age
("bhai, 45 saal" is not pediatrics), which bag-of-words features cannot do well.

## XLM-R joint model (`models/train_xlmr.py`)

One `xlm-roberta-base` encoder with three heads: intent (from `<s>`, class-weighted loss so greet/goodbye count about 10x),
department (from `<s>`, trained only on rows that need routing) and BIO slots (first sub-word of each word).
The best epoch is picked on val (unseen templates); test and free-form are only scored once at the end.
Scoring is identical to `baseline.py`.

| Free-form set (145 msgs) | Intent acc | Intent macro-F1 | Department acc | Slot F1 |
| --- | --- | --- | --- | --- |
| Baseline (TF-IDF + LR, CRF) | 0.66 | 0.66 | 0.91 | 0.69 |
| XLM-R, dept head on all rows (run 1, 4 epochs) | 0.84 | 0.81 | 0.86 | 0.70 |
| **XLM-R, dept head on routed rows (main, 5 epochs)** | **0.82** | **0.81** | **0.91** | **0.72** |
| XLM-R final, trained on train + val, 4 epochs | 0.85 | 0.85 | 0.86 | 0.67 |
| **v2: XLM-R main, trained on train, 5 epochs (picked on val)** | **0.83** | **0.80** | **0.91** | **0.69** |
| v2: XLM-R final, trained on train + val, 5 epochs | 0.80 | 0.77 | 0.88 | 0.69 |

**v2 results (dataset_v2, the current numbers to report).** On unseen-template test the v2 main model scores 0.96 intent
acc, 0.95 macro-F1, 1.00 department and 0.95 slot F1; the v2 final model 0.96, 0.94, 1.00 and 0.96. Val still improved at
epoch 5, so both v2 runs use 5 epochs. On free-form the v2 models match v1 within noise (the free-form labels had no age
slips, so v2 was not expected to move them; the final model is up to 5 messages behind main, which is within noise).
The fix shows on the rows it targets: on the 30 v2 test rows with a child word and an age over 12, the v1 final model's
department head says pediatrics for all 30 (0% correct); the v2 final model gets 29 of 30 right, and both get all 30
rows with an age of 12 or under right (`results/xlmr_v2/age_routing_check.json`).
Scores and logs: `results/xlmr_v2_main/` (main) and `results/xlmr_v2/` (final, with weights). Both trained on a
4-core CPU, seed 13 (42 and 56 minutes).

On the unseen-template test the main model scores 0.94 intent acc, 0.90 macro-F1, 0.99 department and 0.94 slot F1.
Per-script scores, training curves and every free-form mistake are in `results/xlmr_v1/`; run 1 is kept in
`results/xlmr_v1_dept_all_rows/` as an ablation. Both runs were trained on CPU (23 and 29 minutes, seed 13).

What the free-form errors show (`results/xlmr_v1/errors_freeform.jsonl`):
- describe_symptom vs emergency is the biggest confusion (5 of 26 intent errors). Some of these labels are debatable, so
  agree a rule for "severe but not life-threatening" and relabel before the final run.
- Urdu-script free-form is the weakest slice (0.79 intent, 0.63 slot F1). Templates under-cover natural Urdu phrasing.
- Slot F1 on free-form is only slightly above the baseline: span boundaries differ ("aaj hi" vs "aaj"), and symptom
  phrases written naturally are longer than the template ones. More varied training text helps more than a bigger model.
- With 145 messages, one message is 0.7 points, so differences under about 3 points between runs are noise.

```bash
cd models
pip install torch transformers sentencepiece scikit-learn
python train_xlmr.py --data ../data/dataset_v2 --out ../results/xlmr_v2_main --epochs 5 --no_save   # pick epochs on val
python train_xlmr.py --data ../data/dataset_v2 --out ../results/xlmr_v2 --epochs 5 --train_on_val   # final model
python predict_xlmr.py --model_dir ../results/xlmr_v2/model "kal Dr. Ayesha se appointment chahiye"
```

`train_xlmr_colab.ipynb` does the same on Google Colab (upload the `medbook` folder to Drive first).
The v2 final model's weights (trained on train + val, 1.1 GB, `joint_xlmr.pt`) are in `results/xlmr_v2/model/`, and the
backend loads them automatically (newest `results/*/model`). The v1 final model stays in `results/xlmr_final/model/`. So
`predict_xlmr.py` works without retraining. Report the "main" row as the headline result, since its epoch was chosen on
held-out val; the final model differs from it by 2 to 4 free-form messages per metric, which is within noise.

## Model weights in this repository

GitHub rejects files over 100 MB, so model weights are stored as numbered parts under 95 MB each:

| Model | Files | Full size |
|---|---|---|
| v1 final (`results/xlmr_final/model/`) | `joint_xlmr_fp16.pt.part0` to `part5` + `joint_xlmr_fp16.pt.sha256` | 559 MB (fp16) |
| v2 final (`results/xlmr_v2/model/`) | not committed yet: the 1.1 GB `joint_xlmr.pt` was never copied out of the training environment | 1.1 GB (fp32) |

You do not need to reassemble anything to run the code: `models/predict_xlmr.py` (`load_weights`) joins
`joint_xlmr_fp16.pt.part*` in memory and casts back to fp32. To rebuild the single file anyway and check its hash:

```bash
scripts/reassemble_weights.sh                         # every results/*/model
scripts/reassemble_weights.sh results/xlmr_final/model
# or by hand:  cat joint_xlmr_fp16.pt.part{0..5} > joint_xlmr_fp16.pt && sha256sum -c joint_xlmr_fp16.pt.sha256
```

To add the v2 weights after training (on Colab or locally), shrink them to fp16 the same way as v1 (or keep fp32), then split:

```bash
scripts/split_weights.sh results/xlmr_v2/model/joint_xlmr.pt   # writes .part0.. and .sha256; the full file stays gitignored
git add results/xlmr_v2/model/joint_xlmr.pt.part* results/xlmr_v2/model/joint_xlmr.pt.sha256
```

Note: `load_weights` reads split parts only for the fp16 name (`joint_xlmr_fp16.pt.part*`). For fp32 parts, run
`scripts/reassemble_weights.sh` after cloning so `joint_xlmr.pt` exists.

The project proposal is in `docs/MedBook_FYP_Proposal.docx`.

## XLM-R vs a prompted LLM (`results/llm_compare/`)

Same messages, same scoring. Full write-up, per-style tables and how to add Claude or any OpenAI-compatible model:
[`results/llm_compare/README.md`](results/llm_compare/README.md).

| Free-form set (145 msgs) | Intent acc | Department acc | Slot F1 | Median latency (4-core CPU) |
| --- | --- | --- | --- | --- |
| Baseline | 0.66 | 0.91 | 0.69 | 1 ms |
| XLM-R fine-tuned (final) | 0.85 | 0.86 | 0.67 | 28 ms |
| Qwen2.5-7B, few-shot prompt | 0.74 | 0.80 | 0.53 | 10.6 s |
| Qwen2.5-3B, zero-shot prompt | 0.48 | 0.68 | 0.31 | 6.5 s |

## Rebuild

```bash
cd data_gen
python build_dataset.py --out ../data/dataset_v2        # same seed gives the same files
python audit_labels.py ../data/dataset_v2               # label audit, exits 1 if any slip
cd ../models
pip install scikit-learn sklearn-crfsuite
python baseline.py --data ../data/dataset_v2 --out ../results/baseline_v2
```

`paraphrase.py` (an LLM rewording pass) is optional and has not been run, since no API key was available.

## Known limits

- greet and goodbye have only 16 and 14 training rows. Use class weights or oversample them when training.
- Some generated sentences have small grammar slips (for example "ulti ho raha hai", "pregnancy ka ultrasound ke liye kis specialist").
  The 300-row hand audit for v2 found no further label errors, only slips like these.
- The free-form set was written by Claude, not by patients. Replace or extend it with the human-written test set from classmates and family.
- Symptom-to-department mappings still need a check by a doctor.
