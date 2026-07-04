"""Label the synthetic dataset using llama3.1:8b as a teacher.

Reuses the EXACT production system prompt/schema from speakr.formatter so
the student model is trained on the identical task it will run at inference
time. Bad teacher outputs are dropped using the same guardrails already
validated in production (looks_like_answer, length sanity checks) plus a
couple of dataset-specific checks (valid JSON, list_items count).

Usage: python label_dataset.py --in dataset_raw.jsonl --out dataset_labeled.jsonl
"""

import argparse
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from speakr.formatter import RESPONSE_SCHEMA, SYSTEM_PROMPT, assemble_list, looks_like_answer

OLLAMA_URL = "http://127.0.0.1:11434"
MODEL = "llama3.1:8b"


def build_messages(text: str, tone: str, exe: str, title: str):
    app_line = ""
    if exe:
        app_line = f"\nThe user is dictating into {exe}"
        if title:
            app_line += f' (window: "{title[:120]}")'
        app_line += "."
    system = SYSTEM_PROMPT.format(tone=tone, app_line=app_line, recent_line="")
    user = f'Clean this transcript:\n"""\n{text}\n"""'
    return system, user


def label_one(text: str, tone: str, exe: str, title: str):
    system, user = build_messages(text, tone, exe, title)
    resp = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": MODEL,
            "stream": False,
            "keep_alive": "30m",
            "format": RESPONSE_SCHEMA,
            "options": {"temperature": 0.1},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = json.loads(resp.json()["message"]["content"])
    return system, user, data


CORRECTION_CATEGORIES = {"single_correction", "chained_correction"}


def validate(text: str, data: dict, category: str = "") -> str | None:
    """Returns a rejection reason, or None if the label is good.

    Note: the aggressive collapse expected from corrections ("call John, no
    wait Mike, actually Dave" -> "Call Dave.") looks identical to truncation
    by a blunt length-ratio check, so that check is skipped for correction
    categories — looks_like_answer (checks for INTRODUCED words, i.e. actual
    hallucination) is the check that matters there.
    """
    cleaned = (data.get("cleaned") or "").strip()
    if not cleaned:
        return "empty cleaned"
    if len(cleaned) > len(text) * 3 + 60:
        return "output too long (likely hallucinated content)"
    if category not in CORRECTION_CATEGORIES and len(text) > 40 and len(cleaned) < len(text) * 0.2:
        return "output too short (likely dropped content)"
    if looks_like_answer(text, cleaned):
        return "model answered instead of cleaning"
    if data.get("is_list"):
        items = data.get("list_items")
        if not isinstance(items, list) or len(items) < 2:
            return "is_list=true but <2 list_items"
        assembled = assemble_list(data.get("list_intro") or "", [str(i) for i in items])
        if not assembled.strip():
            return "list assembly produced nothing"
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="inp", default="dataset_raw.jsonl")
    parser.add_argument("--out", default="dataset_labeled.jsonl")
    parser.add_argument("--rejected-out", default="dataset_rejected.jsonl")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    rows = [json.loads(l) for l in Path(args.inp).read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.limit:
        rows = rows[: args.limit]

    kept, rejected = 0, 0
    started = time.monotonic()
    with open(args.out, "w", encoding="utf-8") as out_f, \
         open(args.rejected_out, "w", encoding="utf-8") as rej_f:
        for i, row in enumerate(rows):
            text = row["input"]
            tone = row.get("tone", "neutral")
            app_ctx = row.get("app_context", {})
            try:
                system, user, data = label_one(text, tone, app_ctx.get("exe", ""), app_ctx.get("title", ""))
            except Exception as exc:
                rejected += 1
                rej_f.write(json.dumps({"input": text, "reason": f"request failed: {exc}"}) + "\n")
                continue
            reason = validate(text, data, category=row.get("category", ""))
            if reason:
                rejected += 1
                rej_f.write(json.dumps({"input": text, "reason": reason, "label": data}, ensure_ascii=False) + "\n")
                continue
            kept += 1
            out_f.write(json.dumps({
                "input": text,
                "category": row.get("category"),
                "system": system,
                "user": user,
                "assistant": json.dumps(data, ensure_ascii=False),
            }, ensure_ascii=False) + "\n")

            if (i + 1) % 100 == 0:
                elapsed = time.monotonic() - started
                rate = (i + 1) / elapsed
                eta = (len(rows) - i - 1) / rate
                print(f"  {i+1}/{len(rows)} kept={kept} rejected={rejected} "
                      f"({rate:.1f}/s, eta {eta/60:.1f}min)", flush=True)

    print(f"\nDone: {kept} kept, {rejected} rejected ({rejected/(kept+rejected)*100:.1f}% reject rate)")
    print(f"-> {args.out}")
    print(f"-> {args.rejected_out} (for inspection)")


if __name__ == "__main__":
    main()
