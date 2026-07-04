"""Evaluate a candidate Ollama model on two complementary measures:

1. Hard-case suite (training/hard_cases.py) -- the same 12 adversarial
   checks used to pick llama3.1:8b as the pre-fine-tune default.
2. Held-out agreement -- similarity to the llama3.1:8b teacher's output on
   dataset_eval_raw.jsonl, which was generated with a DIFFERENT random seed
   than the training set, so this measures generalization, not memorization.

Usage: python evaluate.py speakr-format llama3.2 llama3.1:8b
"""

import json
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from speakr.config import Config
from speakr.formatter import Formatter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hard_cases import CASES

TEACHER_MODEL = "llama3.1:8b"
CTX = {"exe": "slack.exe", "title": "general - Slack"}


def word_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().split(), b.lower().split()).ratio()


def make_formatter(model_name: str) -> Formatter:
    cfg = Config()
    cfg.data["formatting"]["ollama_model"] = model_name
    return Formatter(cfg)


def run_hard_cases(formatter: Formatter):
    passed, lats = 0, []
    for name, dictation, check in CASES:
        start = time.monotonic()
        try:
            out = formatter.format(dictation, CTX)
        except Exception:
            out = ""
        lats.append(time.monotonic() - start)
        try:
            ok = check(out)
        except Exception:
            ok = False
        passed += ok
    return passed, len(CASES), lats


def run_held_out(formatter: Formatter, teacher_outputs: list[str], rows: list[dict]):
    sims, lats = [], []
    for row, teacher_out in zip(rows, teacher_outputs):
        start = time.monotonic()
        try:
            out = formatter.format(row["input"], row.get("app_context", CTX))
        except Exception:
            out = ""
        lats.append(time.monotonic() - start)
        sims.append(word_similarity(out, teacher_out))
    return sims, lats


def main():
    models = sys.argv[1:]
    if not models:
        print("Usage: python evaluate.py <model> [<model> ...]")
        sys.exit(1)

    eval_path = Path(__file__).parent / "dataset_eval_raw.jsonl"
    rows = [json.loads(l) for l in eval_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    print(f"Computing teacher ({TEACHER_MODEL}) reference outputs on {len(rows)} held-out examples...")
    teacher = make_formatter(TEACHER_MODEL)
    teacher_outputs = [teacher.format(r["input"], r.get("app_context", CTX)) for r in rows]

    results = []
    for model_name in models:
        print(f"\n=== {model_name} ===")
        formatter = make_formatter(model_name)
        if not formatter._ollama_available():
            print("  NOT AVAILABLE, skipping")
            continue

        passed, total, hard_lats = run_hard_cases(formatter)
        print(f"  hard cases: {passed}/{total}")

        sims, held_lats = run_held_out(formatter, teacher_outputs, rows)
        avg_sim = sum(sims) / len(sims)
        low_sim = sum(1 for s in sims if s < 0.6)
        all_lats = hard_lats + held_lats
        avg_lat = sum(all_lats) / len(all_lats)
        p95_lat = sorted(all_lats)[int(len(all_lats) * 0.95)]
        print(f"  held-out agreement with teacher: {avg_sim:.3f} avg "
              f"({low_sim}/{len(sims)} examples <0.6 similarity)")
        print(f"  latency: avg={avg_lat:.2f}s p95={p95_lat:.2f}s")
        results.append({
            "model": model_name, "hard_passed": passed, "hard_total": total,
            "held_out_similarity": avg_sim, "low_sim_count": low_sim,
            "avg_latency": avg_lat, "p95_latency": p95_lat,
        })

    print("\n=== SUMMARY ===")
    print(f"{'model':<20} {'hard':<8} {'similarity':<12} {'avg_lat':<10} {'p95_lat'}")
    for r in sorted(results, key=lambda r: (-r["hard_passed"], -r["held_out_similarity"])):
        print(f"{r['model']:<20} {r['hard_passed']}/{r['hard_total']:<6} "
              f"{r['held_out_similarity']:<12.3f} {r['avg_latency']:<10.2f} {r['p95_latency']:.2f}")


if __name__ == "__main__":
    main()
