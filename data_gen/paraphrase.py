"""LLM paraphrase pass: turn template rows into more natural, varied utterances.

Usage (needs ANTHROPIC_API_KEY, `pip install anthropic`):
    python paraphrase.py --inp ../data/sample/train.jsonl --out ../data/sample/train_para.jsonl \
        --limit 50 --n 4

Every slot value must survive word for word; rows where any value is missing are
dropped. Kept rows are re-tokenised and re-tagged, so labels stay exact.
Run it on TRAIN rows only, and paraphrase each split separately, never across splits.
"""
import argparse
import json
import os

import anthropic

from generate import ROUTED_INTENTS, script_of, tokens_and_tags

MODEL = os.environ.get("MEDBOOK_LLM", "claude-opus-5-5")

PROMPT = """You help build a dataset for a Pakistani clinic booking chatbot.
Rewrite the patient's message {n} different ways, the way real Pakistani patients type
on WhatsApp. Keep the same intent ({intent}) and keep the writing style: {style_note}

Rules:
- Each of these exact strings must appear unchanged in every rewrite: {values}
- Vary word order, politeness (ji, please, plz), filler words and length.
- Do not add new names, dates, times, doctors or symptoms.

Message: {text}"""

STYLE_NOTE = {
    "roman": "Roman Urdu (Latin letters) mixed with English words.",
    "urdu": "Urdu script only.",
    "mixed": "Urdu script with some English words written in English letters.",
}

SCHEMA = {
    "type": "object",
    "properties": {"rewrites": {"type": "array", "items": {"type": "string"}}},
    "required": ["rewrites"],
    "additionalProperties": False,
}


def paraphrase(client, row, n):
    values = [s["value"] for s in row["spans"]]
    resp = client.beta.messages.create(
        model=MODEL,
        max_tokens=2000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",  # re-runs on a fallback model if a request is declined
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": PROMPT.format(
            n=n, intent=row["intent"], style_note=STYLE_NOTE[row["style"]],
            values=json.dumps(values, ensure_ascii=False) if values else "(none)",
            text=row["text"])}],
    )
    if resp.stop_reason == "refusal":
        return []
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)["rewrites"]


def relabel(row, new_text, k):
    spans, cursor = [], 0
    for s in sorted(row["spans"], key=lambda s: s["start"]):
        i = new_text.find(s["value"], cursor)
        if i < 0:
            i = new_text.find(s["value"])
        if i < 0:
            return None  # a slot value was lost or changed: drop this rewrite
        spans.append((i, i + len(s["value"]), s["label"]))
        cursor = i + len(s["value"])
    tokens, tags = tokens_and_tags(new_text, spans)
    return {
        **row,
        "id": f"{row['id']}-p{k}",
        "text": new_text,
        "tokens": tokens,
        "tags": tags,
        "spans": [{"start": a, "end": b, "label": l, "value": new_text[a:b]} for a, b, l in spans],
        "script": script_of(new_text),
        "source": "llm",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--n", type=int, default=4)
    args = ap.parse_args()

    client = anthropic.Anthropic()
    rows = [json.loads(l) for l in open(args.inp, encoding="utf-8")]
    rows = [r for r in rows if r["source"] == "template"][: args.limit]
    kept = dropped = 0
    with open(args.out, "w", encoding="utf-8") as f:
        for row in rows:
            for k, new in enumerate(paraphrase(client, row, args.n)):
                new_row = relabel(row, new.strip(), k)
                if new_row is None:
                    dropped += 1
                    continue
                assert new_row["intent"] in ROUTED_INTENTS or new_row["department"] == "none"
                f.write(json.dumps(new_row, ensure_ascii=False) + "\n")
                kept += 1
    print(f"kept {kept}, dropped {dropped} (slot value not preserved)")


if __name__ == "__main__":
    main()
