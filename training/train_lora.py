"""QLoRA fine-tune of Qwen2.5-3B-Instruct on the labeled dictation-cleanup
dataset. Produces a LoRA adapter under training/adapter/ which
export_gguf.py then merges and converts for Ollama.

--eval-data MUST be a genuinely held-out split (different generator seed
than --data), not an in-distribution slice of the training file -- that was
round 1's bug: an in-distribution eval split saturates to near-zero loss
right alongside training loss, hiding overfitting instead of catching it.

Usage: python train_lora.py --data dataset_train_labeled.jsonl --eval-data dataset_val_labeled.jsonl
"""

import argparse
import json
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, EarlyStoppingCallback
from trl import SFTConfig, SFTTrainer

MODEL_ID = "Qwen/Qwen2.5-3B-Instruct"


def load_examples(path: str) -> Dataset:
    rows = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    examples = [{
        "messages": [
            {"role": "system", "content": r["system"]},
            {"role": "user", "content": r["user"]},
            {"role": "assistant", "content": r["assistant"]},
        ]
    } for r in rows]
    return Dataset.from_list(examples)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="training/dataset_train_labeled.jsonl")
    parser.add_argument(
        "--eval-data", default="training/dataset_val_labeled.jsonl",
        help="Genuinely held-out set (different generator seed than --data). "
             "Round 1's bug: evaluating on an in-distribution split let the "
             "model overfit undetected, since that split saturated to "
             "near-zero loss right alongside training loss.",
    )
    parser.add_argument("--out", default="training/adapter")
    parser.add_argument("--epochs", type=float, default=3)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--max-length", type=int, default=768)
    parser.add_argument("--eval-steps", type=int, default=20)
    parser.add_argument("--early-stopping-patience", type=int, default=4)
    args = parser.parse_args()

    train_ds = load_examples(args.data)
    val_ds = load_examples(args.eval_data)
    print(f"Train: {len(train_ds)}  Val (held-out, different seed): {len(val_ds)}")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, quantization_config=bnb_config, device_map="auto",
    )
    model.config.use_cache = False

    lora_config = LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    sft_config = SFTConfig(
        output_dir=args.out,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.05,
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=args.eval_steps,
        save_strategy="steps",
        save_steps=args.eval_steps,
        save_total_limit=3,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        bf16=True,
        max_length=args.max_length,
        report_to=[],
        packing=False,
    )
    # Round 1 trained straight through 516 steps after loss had already
    # saturated by step 40 -- pure overfitting. This time, stop automatically
    # once the GENUINELY held-out eval_loss hasn't improved for N evals,
    # instead of trusting a fixed epoch count.
    trainer = SFTTrainer(
        model=model, args=sft_config,
        train_dataset=train_ds, eval_dataset=val_ds,
        processing_class=tokenizer,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=args.early_stopping_patience)],
    )
    trainer.train()

    final_dir = f"{args.out}_final"
    trainer.save_model(final_dir)
    tokenizer.save_pretrained(final_dir)
    print(f"Adapter saved to {final_dir}")


if __name__ == "__main__":
    main()
