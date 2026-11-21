### Free-form set (145 hand-written messages)

| Model | Intent acc | Intent macro-F1 | Department acc | Slot F1 (exact) | Slot F1 (relaxed) |
| --- | --- | --- | --- | --- | --- |
| Baseline (TF-IDF + LR, CRF) | 0.66 | 0.66 | 0.91 | 0.69 | 0.82 |
| XLM-R fine-tuned (final model) | 0.85 | 0.85 | 0.86 | 0.67 | 0.86 |
| qwen2.5-3b few-shot | 0.66 | 0.71 | 0.66 | 0.46 | 0.56 |
| qwen2.5-3b zero-shot | 0.48 | 0.55 | 0.68 | 0.31 | 0.38 |
| qwen2.5-7b few-shot | 0.74 | 0.79 | 0.80 | 0.53 | 0.74 |

**By writing style (freeform): intent accuracy / department accuracy / exact slot F1**

| Model | Roman Urdu | Urdu script | Urdu + English (mixed) |
| --- | --- | --- | --- |
| Baseline (TF-IDF + LR, CRF) | 0.68 / 0.84 / 0.68 | 0.57 / 0.95 / 0.67 | 0.72 / 1.00 / 0.73 |
| XLM-R fine-tuned (final model) | 0.83 / 0.88 / 0.73 | 0.86 / 0.79 / 0.54 | 0.88 / 0.92 / 0.69 |
| qwen2.5-3b few-shot | 0.67 / 0.64 / 0.46 | 0.60 / 0.63 / 0.46 | 0.76 / 0.75 / 0.47 |
| qwen2.5-3b zero-shot | 0.45 / 0.72 / 0.32 | 0.48 / 0.58 / 0.27 | 0.60 / 0.75 / 0.32 |
| qwen2.5-7b few-shot | 0.74 / 0.88 / 0.56 | 0.76 / 0.58 / 0.46 | 0.68 / 1.00 / 0.56 |

### Unseen-template test, stratified sample (300 messages)

| Model | Intent acc | Intent macro-F1 | Department acc | Slot F1 (exact) | Slot F1 (relaxed) |
| --- | --- | --- | --- | --- | --- |
| Baseline (TF-IDF + LR, CRF) | 0.71 | 0.70 | 1.00 | 0.93 | 0.96 |
| XLM-R fine-tuned (final model) | 0.99 | 0.99 | 1.00 | 0.90 | 0.95 |
| qwen2.5-3b few-shot | 0.74 | 0.71 | 0.59 | 0.64 | 0.72 |
| qwen2.5-3b zero-shot | 0.54 | 0.54 | 0.57 | 0.42 | 0.50 |
| qwen2.5-7b few-shot | 0.77 | 0.79 | 0.71 | 0.77 | 0.83 |

**By writing style (test): intent accuracy / department accuracy / exact slot F1**

| Model | Roman Urdu | Urdu script | Urdu + English (mixed) |
| --- | --- | --- | --- |
| Baseline (TF-IDF + LR, CRF) | 0.71 / 1.00 / 0.89 | 0.69 / 1.00 / 0.93 | 0.74 / 1.00 / 0.99 |
| XLM-R fine-tuned (final model) | 0.99 / 1.00 / 0.83 | 0.98 / 1.00 / 0.98 | 1.00 / 1.00 / 0.95 |
| qwen2.5-3b few-shot | 0.80 / 0.52 / 0.67 | 0.70 / 0.51 / 0.64 | 0.68 / 0.79 / 0.58 |
| qwen2.5-3b zero-shot | 0.62 / 0.31 / 0.49 | 0.46 / 0.57 / 0.40 | 0.46 / 0.88 / 0.31 |
| qwen2.5-7b few-shot | 0.90 / 0.86 / 0.79 | 0.63 / 0.62 / 0.78 | 0.71 / 0.67 / 0.73 |

### Latency and cost per message

| Model | Hardware | Median latency | p95 latency | Tokens in / out | Cost per 1,000 messages |
| --- | --- | --- | --- | --- | --- |
| Baseline (TF-IDF + LR, CRF) | CPU, 4 cores | 1 ms | 1 ms | n/a | $0 (local) |
| XLM-R fine-tuned (final model) | CPU, 4 cores | 28 ms | 41 ms | n/a | $0 (local) |
| qwen2.5-3b few-shot | CPU, 4 cores | 5.8 s | 9.5 s | 3126 / 39 | $0 (local) |
| qwen2.5-3b zero-shot | CPU, 4 cores | 6.5 s | 11.8 s | 1214 / 45 | $0 (local) |
| qwen2.5-7b few-shot | CPU, 4 cores | 10.6 s | 17.3 s | 3126 / 39 | $0 (local) |
