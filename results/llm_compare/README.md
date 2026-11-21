# Fine-tuned XLM-R vs a prompted LLM

Evaluation-chapter experiment: can a general instruction-tuned LLM, given only a prompt (zero-shot) or a prompt
plus 33 labelled examples (few-shot), replace the fine-tuned XLM-R NLU? Every model below parsed exactly the same
messages, one message at a time, and was scored with the same code (`models/llm_eval.py`, which reproduces
`baseline.py` / `train_xlmr.py` scoring: the baseline and XLM-R rows match their earlier `scores.json` exactly).

## Short answer

No. The fine-tuned XLM-R is more accurate on every main metric, about 400 times faster and free to run.
The best open LLM tried (Qwen2.5 7B, few-shot) gets 0.74 intent accuracy on the free-form set against 0.85 for
XLM-R (McNemar on the 145 messages: 28 messages only XLM-R gets right vs 12 only the LLM gets right, p ≈ 0.02),
and takes about 11 s per message on a 4-core CPU against 28 ms. It does have one real strength: it understands
naturally phrased symptoms that the templates never covered (see "Where the LLM wins").

## Setup

| | |
| --- | --- |
| Test sets | `test_freeform.jsonl` (all 145 hand-written messages) and a 300-message sample of `test.jsonl` (unseen templates), stratified by writing style and intent, seed 13 |
| LLMs | Qwen2.5-3B-Instruct and Qwen2.5-7B-Instruct, 4-bit GGUF (Q4_K_M), run locally with llama.cpp. Open weights, Apache-2.0, multilingual incl. Urdu. No API key was available, so no hosted model was run here |
| Prompt | Intent definitions from `schema.py`, one line of typical complaints per department, the clinic's 16-doctor directory (so a named doctor can be routed), slot definitions and span rules. Few-shot adds 33 training rows (2 per intent in different scripts + 1 per missing department). Full prompts are in each run's `system_prompt.txt` |
| Output | JSON constrained by a grammar (`{"intent", "department", "slots": [{"label", "value"}]}`), temperature 0. 0 invalid replies in all runs |
| Slots | Each predicted value is located in the gold tokens. Exact F1 needs the same span boundaries as the gold label; relaxed F1 counts same label + overlapping tokens. Values not found in the message count as false positives |
| Department | Accuracy on messages that carry a routing label, as before |
| Hardware | Same 4-core CPU for every model, no GPU. Latency is wall time per message, one message at a time |

## Results

### Free-form set (145 hand-written messages)

| Model | Intent acc | Intent macro-F1 | Department acc | Slot F1 (exact) | Slot F1 (relaxed) |
| --- | --- | --- | --- | --- | --- |
| Baseline (TF-IDF + LR, CRF) | 0.66 | 0.66 | **0.91** | **0.69** | 0.82 |
| **XLM-R fine-tuned (final model)** | **0.85** | **0.85** | 0.86 | 0.67 | **0.86** |
| Qwen2.5-3B zero-shot | 0.48 | 0.55 | 0.68 | 0.31 | 0.38 |
| Qwen2.5-3B few-shot | 0.66 | 0.71 | 0.66 | 0.46 | 0.56 |
| Qwen2.5-7B few-shot | 0.74 | 0.79 | 0.80 | 0.53 | 0.74 |

### Unseen-template test, stratified sample (300 messages)

| Model | Intent acc | Intent macro-F1 | Department acc | Slot F1 (exact) | Slot F1 (relaxed) |
| --- | --- | --- | --- | --- | --- |
| Baseline (TF-IDF + LR, CRF) | 0.71 | 0.70 | **1.00** | **0.93** | **0.96** |
| **XLM-R fine-tuned (final model)** | **0.99** | **0.99** | **1.00** | 0.90 | 0.95 |
| Qwen2.5-3B zero-shot | 0.54 | 0.54 | 0.57 | 0.42 | 0.50 |
| Qwen2.5-3B few-shot | 0.74 | 0.71 | 0.59 | 0.64 | 0.72 |
| Qwen2.5-7B few-shot | 0.77 | 0.79 | 0.71 | 0.77 | 0.83 |

### By writing style (intent accuracy / department accuracy / exact slot F1)

Free-form set:

| Model | Roman Urdu (78) | Urdu script (42) | Urdu + English (25) |
| --- | --- | --- | --- |
| Baseline | 0.68 / 0.84 / 0.68 | 0.57 / 0.95 / 0.67 | 0.72 / 1.00 / 0.73 |
| XLM-R fine-tuned | 0.83 / 0.88 / 0.73 | 0.86 / 0.79 / 0.54 | 0.88 / 0.92 / 0.69 |
| Qwen2.5-3B zero-shot | 0.45 / 0.72 / 0.32 | 0.48 / 0.58 / 0.27 | 0.60 / 0.75 / 0.32 |
| Qwen2.5-3B few-shot | 0.67 / 0.64 / 0.46 | 0.60 / 0.63 / 0.46 | 0.76 / 0.75 / 0.47 |
| Qwen2.5-7B few-shot | 0.74 / 0.88 / 0.56 | 0.76 / 0.58 / 0.46 | 0.68 / 1.00 / 0.56 |

Test sample:

| Model | Roman Urdu (143) | Urdu script (89) | Urdu + English (68) |
| --- | --- | --- | --- |
| Baseline | 0.71 / 1.00 / 0.89 | 0.69 / 1.00 / 0.93 | 0.74 / 1.00 / 0.99 |
| XLM-R fine-tuned | 0.99 / 1.00 / 0.83 | 0.98 / 1.00 / 0.98 | 1.00 / 1.00 / 0.95 |
| Qwen2.5-3B zero-shot | 0.62 / 0.31 / 0.49 | 0.46 / 0.57 / 0.40 | 0.46 / 0.88 / 0.31 |
| Qwen2.5-3B few-shot | 0.80 / 0.52 / 0.67 | 0.70 / 0.51 / 0.64 | 0.68 / 0.79 / 0.58 |
| Qwen2.5-7B few-shot | 0.90 / 0.86 / 0.79 | 0.63 / 0.62 / 0.78 | 0.71 / 0.67 / 0.73 |

Per-style slices are small (25 to 143 messages), so read them as direction, not as exact numbers.

### Latency and cost per message

| Model | Runs on | Median latency | p95 latency | Tokens in / out | Cost per 1,000 messages |
| --- | --- | --- | --- | --- | --- |
| Baseline | CPU, 4 cores | 1 ms | 1 ms | n/a | $0 |
| XLM-R fine-tuned | CPU, 4 cores | 28 ms | 41 ms | n/a | $0 |
| Qwen2.5-3B zero-shot | CPU, 4 cores | 6.5 s | 11.8 s | 1,214 / 45 | $0 (local) |
| Qwen2.5-3B few-shot | CPU, 4 cores | 5.8 s | 9.5 s | 3,126 / 39 | $0 (local) |
| Qwen2.5-7B few-shot | CPU, 4 cores | 10.6 s | 17.3 s | 3,126 / 39 | $0 (local) |

The few-shot prompt is not slower than zero-shot even though it is 2.5x longer, because llama.cpp reuses the
processed prompt prefix between messages (only the first message pays for it) and the examples make replies shorter. On a GPU the LLMs would be roughly 10x faster,
but still about 100x slower than XLM-R on the same CPU.

**Projected API cost** (not measured: no key was available here). With the same few-shot prompt
(about 3,100 input tokens, of which about 3,050 are the fixed instructions and can be cached, and about 40 output
tokens), at Anthropic's November 2026 list prices:

| Model | Cost per 1,000 messages, prompt cached | Without caching |
| --- | --- | --- |
| Claude Haiku 5.5 ($0.10 / $0.50 per M tokens) | about $0.06 | about $0.33 |
| Claude Sonnet 5.5 ($2 / $10) | about $1.20 | about $6.70 |
| Claude Opus 5.5 ($4 / $20) | about $2.30 | about $13 |

These use Qwen's token counts; Claude's tokenizer counts Urdu script differently, so treat them as order of magnitude.
Running `llm_eval.py --backend anthropic` reports the real token counts and cost.

## What the numbers show

1. **Fine-tuning wins clearly.** XLM-R (270M parameters) beats a 7B LLM by 11 points of intent accuracy on free-form
   text and by 22 points on unseen templates, and it is about 400x faster on the same hardware. For a clinic bot
   that must answer in under a second on a cheap server, the LLM is not an option without a GPU or a paid API.
2. **Bigger and few-shot both matter a lot for the LLM.** 3B zero-shot → 3B few-shot → 7B few-shot goes 0.48 → 0.66 →
   0.74 on free-form intent. Zero-shot the 3B model does not learn the label conventions (for example, that "fever,
   please let a doctor see me today" is `book_appointment`, not `describe_symptom`).
3. **Exact slot F1 is low for LLMs mostly because of span boundaries and copying.** The 7B model's relaxed slot F1
   (0.74 free-form, 0.83 test) is well above its exact F1. Typical misses: it trims the span ("9 baje" for
   "saade 9 baje", "dopahar" for "dopahar ko", "درد" for "جسم میں درد"); it rewrites the value instead of copying it
   ("dr adeel qureshi" returned as "ڈاکٹر عدیل قریشی", "raat 8 baje" as "راات 8 باجه"); and it tags relatives as
   PATIENT_NAME ("چھوٹی بہن", "بیٹی"). A fine-tuned tagger learns the annotation rules and cannot rewrite text.
4. **Department routing is weaker for the LLM, even with the doctor directory in the prompt.** On the test sample the
   7B model routes 71% correctly vs 100% for XLM-R, and most misses are in Urdu script: "مجھے کمر درد ہے" → ENT instead
   of orthopedics, "ماہواری کا مسئلہ" → GP instead of gynecology, "ڈاکٹر طارق محمود" → orthopedics although the prompt
   lists him under ENT. It answers "none" on only 8 of the 90 routed messages, so the misses are real wrong routes.
5. **Urdu script is the weakest style for the LLM's routing** (department 0.58 free-form, 0.62 test for the 7B model)
   and for its intent on the test sample (0.63), while XLM-R stays at 0.98 or above on test intent in every style.

### Where the LLM wins

The two models make different mistakes. On the free-form set only 10 messages are wrong for both; the LLM is right on
12 messages XLM-R gets wrong, mostly natural symptom descriptions that no template resembles:

- "subah uthte hi chakkar aata hai aur ji matlata hai", "gir gaya tha, ab kalai hila nahi pa raha",
  "کندھا اوپر نہیں اٹھتا", "throat میں pain ہے اور آواز بھی نہیں نکل رہی" (XLM-R: wrong intent, LLM: describe_symptom)
- "my father is having a heart attack please help" (XLM-R misses the emergency, the LLM catches it)

Per intent on the free-form set, the 7B LLM gets describe_symptom 95% right (XLM-R 67%) but book_appointment only 38%
(XLM-R 82%): it reads "bukhar hai, doctor dekh le" as a symptom, not a booking. That is the labelling convention, not
language understanding, and few-shot examples only partly fix it.

This suggests two uses for an LLM in the project that are cheaper than putting it in the chat loop:
- **Data augmentation**: use an LLM to paraphrase training rows into natural phrasing (`data_gen/paraphrase.py`
  already does this) and retrain XLM-R, which keeps the 28 ms runtime.
- **Fallback**: call the LLM only when XLM-R's intent confidence is low. Not tested here.

### Dataset note found during this check

At least one test label looks wrong: "hello، میرے بھانجے کی age 25 saal ہے، اسے fever ہے" is labelled pediatrics,
but a 25-year-old is an adult (the LLM said general_physician). The child-symptom templates do not check the age
value. Worth fixing in `data_gen/templates.py` before the final run.

## Limits

- Only open models up to 7B, 4-bit quantised, on CPU. A large hosted model (Claude, GPT, Llama 3.3 70B) will
  score higher; run it with the commands below and add the row.
- The few-shot examples are 33 fixed training rows. Choosing examples per message (nearest neighbours) usually helps
  LLMs and was not tried.
- 145 free-form messages: one message is 0.7 points.
- MASSIVE Urdu pre-training (the optional ablation) was not run. It needs a second XLM-R training run of about
  45 minutes on CPU plus a change to `train_xlmr.py` to start from a checkpoint, and this machine was busy with the LLM
  runs. It is a good Colab experiment: fine-tune on MASSIVE `ur-PK` intents first, then on MedBook, and compare the
  free-form row.

## Reproduce or add a model

```bash
cd models
pip install llama-cpp-python scikit-learn sklearn-crfsuite torch transformers sentencepiece

# local open model, no key (about 1 h for both sets on a 4-core CPU)
huggingface-cli download Qwen/Qwen2.5-7B-Instruct-GGUF --include "qwen2.5-7b-instruct-q4_k_m*" --local-dir ~/llm
python llm_eval.py --backend llamacpp --model ~/llm/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf \
    --shots few --out ../results/llm_compare/qwen2.5-7b_few

# Claude (pip install anthropic)
export ANTHROPIC_API_KEY=...
python llm_eval.py --backend anthropic --model claude-haiku-5-5 --shots few --out ../results/llm_compare/claude-haiku-5-5_few

# any OpenAI-compatible API, e.g. Groq's free tier (pip install openai)
export OPENAI_API_KEY=... OPENAI_BASE_URL=https://api.groq.com/openai/v1
python llm_eval.py --backend openai --model llama-3.3-70b-versatile --shots few --json_mode object \
    --price_in 0.59 --price_out 0.79 --out ../results/llm_compare/llama-3.3-70b_few

# baseline + XLM-R on the same messages, with latency
python local_eval.py --out ../results/llm_compare

# rebuild the tables from every run folder
python llm_compare_table.py > ../results/llm_compare/tables.md
```

`--test_n 0` scores all 1,451 test rows instead of the 300 sample. Runs resume where they stopped, so a rate limit or
a closed laptop loses nothing. When you add the human-written test set, give it the same row format and point
`--data` at a folder that holds it as `test_freeform.jsonl`.

## Files

| Path | What |
| --- | --- |
| `models/llm_eval.py` | The LLM evaluation (three backends, prompt, scoring, latency, cost) |
| `models/local_eval.py` | Baseline and XLM-R on the same messages, with latency |
| `models/llm_compare_table.py` | Builds `tables.md` from all runs |
| `<run>/scores.json` | Overall and per-style scores, latency, tokens, cost |
| `<run>/predictions_*.jsonl` | Raw reply, latency and tokens for every message |
| `<run>/errors_*.jsonl` | Every message with a wrong intent or department |
| `<run>/system_prompt.txt`, `config.json` | Exact prompt and settings |
